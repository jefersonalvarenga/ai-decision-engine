"""
test_full_conversation.py — Full multi-turn conversation tests for the Gatekeeper agent.

Two modes:
  --local        Uses the internal DSPy ReceptionistSimulator (6 scenarios, no webhook needed)
  --webhook URL  Uses an external webhook receptionist with 5 profiles × 5 policies = 25 combos

Usage examples:
  # Local mode — all 6 DSPy scenarios, verbose
  python -m app.agents.sdr.test_full_conversation --local --verbose

  # Local mode — specific scenario
  python -m app.agents.sdr.test_full_conversation --local --scenario cooperative --verbose

  # Webhook mode — smoke test (1 conversa, profile/policy random)
  python -m app.agents.sdr.test_full_conversation --webhook http://localhost:5678/webhook/receptionist --verbose

  # Webhook mode — specific profile/policy combo
  python -m app.agents.sdr.test_full_conversation --webhook http://... --profile blocker --policy FILTER_FIRST --verbose

  # Webhook mode — all 25 combos
  python -m app.agents.sdr.test_full_conversation --webhook http://... --all-combos

  # Multiple runs per combo (measures variance)
  python -m app.agents.sdr.test_full_conversation --webhook http://... --all-combos --runs 3
"""

import os
import sys
import argparse
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()
ROOT_DIR   = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


# ============================================================================
# PERSONAS (webhook mode)
# ============================================================================

GATEKEEPER_PROFILES = ["blocker", "curious", "helpful", "busy", "protocol"]
CLINIC_POLICIES     = [
    "FILTER_FIRST",
    "NO_DIRECT_CONTACT",
    "EMAIL_GATE",
    "OPEN_TO_PARTNERS",
    "STRICT_TRIAGE",
]

# Clinic names for variety
CLINIC_NAMES = [
    "Clínica Bella Vita",
    "Centro Odontológico São Paulo",
    "Clínica Estética Prime",
    "Dermoclínica Saúde",
    "Odonto Express",
    "Clínica Dr. Silva",
    "Instituto de Estética Avançada",
    "Clínica Oral Care",
]


# ============================================================================
# LOGGER
# ============================================================================

class TeeLogger:
    """Writes simultaneously to terminal and a log file."""

    def __init__(self, log_path: Path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()
        sys.stdout = self.terminal


def setup_logger(mode: str) -> TeeLogger:
    logs_dir = SCRIPT_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{timestamp}_full_conversation_{mode}.log"
    logger    = TeeLogger(logs_dir / filename)
    sys.stdout = logger
    print(f"📝 Log: logs/{filename}\n")
    return logger


# ============================================================================
# WEBHOOK RECEPTIONIST CLIENT
# ============================================================================

class WebhookReceptionistClient:
    """
    HTTP client for the external receptionist simulator webhook.

    Expected request body (POST JSON):
        {
            "message":              "Sofia's latest message",
            "conversation_history": [...],
            "gatekeeper_profile":   "blocker",       # optional — force initial profile
            "clinic_policy":        "FILTER_FIRST",  # optional — force initial policy
            "clinic_name":          "Clínica X",
            "turn_number":          1
        }

    Expected response body (JSON):
        {
            "name":               "gatekeeper",
            "reply":              "mensagem da recepção",
            "gatekeeper_profile": "blocker",
            "clinic_policy":      "FILTER_FIRST",
            "intent_detected":    "commercial_approach",
            "confidence":         0.85
        }

    If your webhook uses different field names, adjust the normalization in `respond()`.
    """

    def __init__(self, webhook_url: str, timeout: int = 30):
        self.webhook_url = webhook_url
        self.timeout     = timeout

    def respond(
        self,
        message: str,
        conversation_history: list,
        gatekeeper_profile: Optional[str] = None,
        clinic_policy: Optional[str] = None,
        clinic_name: str = "Clínica Teste",
        turn_number: int = 1,
    ) -> dict:
        """
        POST to the webhook and return the parsed response dict.

        Returns:
            {
                "reply":              str,
                "gatekeeper_profile": str,
                "clinic_policy":      str,
                "intent_detected":    str,
                "confidence":         float,
                "conversation_ended": bool
            }
        """
        payload = {
            "message":              message,
            "conversation_history": conversation_history,
            "clinic_name":          clinic_name,
            "turn_number":          turn_number,
        }
        if gatekeeper_profile:
            payload["gatekeeper_profile"] = gatekeeper_profile
        if clinic_policy:
            payload["clinic_policy"] = clinic_policy

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Normalize — support both "reply" and alternative keys
            reply = (
                data.get("reply")
                or data.get("response")
                or data.get("message")
                or ""
            ).strip()

            # Infer conversation_ended from intent if not explicitly provided
            confidence = float(data.get("confidence", 0.5))
            intent     = str(data.get("intent_detected", "")).lower()
            ended_kws  = ["farewell", "ending", "goodbye", "encerrar", "despedida", "rejection"]
            conversation_ended = (
                data.get("conversation_ended", False)
                or any(kw in intent for kw in ended_kws)
            )

            return {
                "reply":              reply,
                "gatekeeper_profile": data.get("gatekeeper_profile", gatekeeper_profile or "unknown"),
                "clinic_policy":      data.get("clinic_policy", clinic_policy or "unknown"),
                "intent_detected":    data.get("intent_detected", ""),
                "confidence":         confidence,
                "conversation_ended": bool(conversation_ended),
                "raw":                data,
            }

        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Nao foi possivel conectar ao webhook: {self.webhook_url}\n"
                f"   Verifique se o servidor esta rodando."
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Webhook timeout apos {self.timeout}s: {self.webhook_url}"
            )
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Webhook HTTP error: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Webhook returned invalid JSON: {e}")


# ============================================================================
# SCORING
# ============================================================================

def score_conversation(
    final_stage: str,
    contact_captured: Optional[str],
    email_captured: Optional[str],
    goodbye_sent: bool,
    timed_out: bool,
    agent_turn_count: int,
    objection_turn_count: int,
) -> tuple:
    """Score a completed conversation. Returns (score: float, label: str)."""
    insistent       = objection_turn_count > 2
    graceful_denied = final_stage in ("failed", "denied") and goodbye_sent
    stuck           = timed_out or final_stage not in ["success", "failed", "denied"]

    # Blocking risk overrides all positive outcomes
    if insistent and not contact_captured and not email_captured:
        return -0.30, "BLOCKED_RISK"

    if contact_captured:
        return (1.00, "SUCCESS") if agent_turn_count <= 4 else (0.75, "SUCCESS_SLOW")

    if email_captured:
        return (0.85, "EMAIL_SUCCESS") if agent_turn_count <= 4 else (0.65, "EMAIL_SUCCESS_SLOW")

    if graceful_denied:
        return (0.70, "GRACEFUL_DENIED") if objection_turn_count <= 2 else (0.30, "SLOW_EXIT")

    if stuck:
        return 0.00, "STUCK"

    return 0.10, "UNRESOLVED"


# ============================================================================
# CONVERSATION RUNNER — WEBHOOK MODE
# ============================================================================

MAX_TURNS = 12  # Hard safety limit to prevent infinite loops


def run_webhook_conversation(
    gatekeeper,
    client: WebhookReceptionistClient,
    clinic_name: str,
    gatekeeper_profile: Optional[str],
    clinic_policy: Optional[str],
    current_hour: int = 10,
    verbose: bool = False,
    delay_between_turns: float = 1.0,
) -> dict:
    """
    Run a full SDR <-> Webhook-Receptionist conversation.

    Returns a result dict with outcome, score, and full conversation transcript.
    """
    history: list[dict] = []
    turns:   list[dict] = []
    agent_turn_count     = 0
    objection_turn_count = 0
    final_stage          = "opening"
    contact_captured     = None
    email_captured       = None
    goodbye_sent         = False
    timed_out            = False
    actual_profile       = gatekeeper_profile or "unknown"
    actual_policy        = clinic_policy or "unknown"
    start_time           = time.time()

    if verbose:
        p = gatekeeper_profile or "random"
        q = clinic_policy or "random"
        print(f"\n  [{clinic_name}  profile={p}  policy={q}]")
        print(f"  {'─'*56}")

    for turn_idx in range(MAX_TURNS):

        # ─── Sofia's turn ─────────────────────────────────────────────────
        sofia_result = gatekeeper.forward(
            clinic_name=clinic_name,
            conversation_history=history.copy(),
            latest_message=history[-1]["content"] if history else None,
            current_hour=current_hour,
            current_weekday=datetime.now().weekday(),
            attempt_count=agent_turn_count,
        )

        stage       = sofia_result["conversation_stage"]
        response    = sofia_result.get("response_message", "").strip()
        should_send = sofia_result.get("should_send_message", False)
        final_stage = stage

        if sofia_result.get("extracted_manager_contact"):
            contact_captured = sofia_result["extracted_manager_contact"]
        if sofia_result.get("extracted_manager_email"):
            email_captured = sofia_result["extracted_manager_email"]
        if stage == "handling_objection":
            objection_turn_count += 1
        if stage == "failed" and should_send and response:
            goodbye_sent = True

        if response and should_send:
            turns.append({"role": "agent", "content": response, "stage": stage})
            history.append({"role": "agent", "content": response})
            agent_turn_count += 1
            if verbose:
                print(f"  Sofia [{stage}]: {response}")

        # Terminal — stop after Sofia sends last message
        if stage in ["success", "failed"]:
            break

        if not should_send:
            if verbose:
                print(f"  Sofia aguardando (should_send=False, stage={stage})")

        # ─── Webhook Receptionist's turn ──────────────────────────────────
        if delay_between_turns > 0:
            time.sleep(delay_between_turns)

        rec_result = client.respond(
            message=response or "(sem mensagem)",
            conversation_history=history.copy(),
            gatekeeper_profile=gatekeeper_profile,
            clinic_policy=clinic_policy,
            clinic_name=clinic_name,
            turn_number=turn_idx + 1,
        )

        rec_reply = rec_result["reply"]
        rec_ended = rec_result["conversation_ended"]

        # Update observed profile/policy from webhook response
        actual_profile = rec_result.get("gatekeeper_profile", actual_profile)
        actual_policy  = rec_result.get("clinic_policy", actual_policy)

        if rec_reply:
            turns.append({
                "role":               "human",
                "content":            rec_reply,
                "gatekeeper_profile": actual_profile,
                "clinic_policy":      actual_policy,
                "intent_detected":    rec_result.get("intent_detected", ""),
                "confidence":         rec_result.get("confidence", 0.5),
            })
            history.append({"role": "human", "content": rec_reply})
            if verbose:
                intent_str = rec_result.get("intent_detected", "")
                conf       = rec_result.get("confidence", 0.5)
                extra = f"  [intent={intent_str}  conf={conf:.2f}]" if intent_str else ""
                print(f"  Recepção [{actual_profile}/{actual_policy}]: {rec_reply}{extra}")

        if rec_ended:
            if verbose:
                print("  [Recepcionista encerrou]")
            break

    else:
        timed_out = True
        if verbose:
            print(f"  [Timeout: {MAX_TURNS} turnos sem resolucao]")

    duration_ms = (time.time() - start_time) * 1000
    score, label = score_conversation(
        final_stage=final_stage,
        contact_captured=contact_captured,
        email_captured=email_captured,
        goodbye_sent=goodbye_sent,
        timed_out=timed_out,
        agent_turn_count=agent_turn_count,
        objection_turn_count=objection_turn_count,
    )

    if verbose:
        emoji = "OK" if score >= 0.7 else ("WARN" if score >= 0.3 else "FAIL")
        print(f"\n  [{emoji}] score={score:.2f} ({label})  turns={agent_turn_count}  {duration_ms/1000:.1f}s\n")

    return {
        "clinic_name":          clinic_name,
        "gatekeeper_profile":   actual_profile,
        "clinic_policy":        actual_policy,
        "final_stage":          final_stage,
        "contact_captured":     contact_captured,
        "email_captured":       email_captured,
        "goodbye_sent":         goodbye_sent,
        "timed_out":            timed_out,
        "agent_turn_count":     agent_turn_count,
        "objection_turn_count": objection_turn_count,
        "score":                score,
        "score_label":          label,
        "duration_ms":          round(duration_ms, 1),
        "conversation":         turns,
    }


# ============================================================================
# MATRIX + SUMMARY REPORTS
# ============================================================================

def _score_emoji(score: float) -> str:
    if score >= 0.70:
        return "OK  "
    if score >= 0.30:
        return "WARN"
    return "FAIL"


def print_matrix(results: list) -> None:
    """Print a profile x policy score matrix."""
    if not results:
        return

    profiles = GATEKEEPER_PROFILES
    policies = CLINIC_POLICIES

    # Aggregate scores per cell
    cell: dict = {}
    for r in results:
        key = (r["gatekeeper_profile"], r["clinic_policy"])
        cell.setdefault(key, []).append(r["score"])

    avg_cell = {k: round(sum(v) / len(v), 2) for k, v in cell.items()}

    col_w  = 20
    row_lbl = 12

    print("\n" + "─" * 60)
    print("  MATRIZ: score medio por profile x policy")
    print("  (OK >= 0.70 | WARN >= 0.30 | FAIL < 0.30)")
    print("─" * 60)

    # Header
    header = " " * (row_lbl + 2)
    for pol in policies:
        truncated = pol[:col_w - 1]
        header += truncated.rjust(col_w)
    print(header)
    print("  " + "─" * (row_lbl + col_w * len(policies)))

    for profile in profiles:
        row = "  " + profile.ljust(row_lbl)
        for policy in policies:
            v = avg_cell.get((profile, policy))
            if v is None:
                cell_str = "—"
            else:
                cell_str = _score_emoji(v) + " " + str(v)
            row += cell_str.rjust(col_w)
        print(row)


def print_summary(results: list) -> None:
    """Print aggregate statistics."""
    if not results:
        print("(sem resultados)")
        return

    scores  = [r["score"] for r in results]
    avg     = sum(scores) / len(scores)
    passed  = sum(1 for r in results if r["score"] >= 0.70)
    blocked = sum(1 for r in results if r["score_label"] == "BLOCKED_RISK")

    label_counts: dict = {}
    for r in results:
        label_counts[r["score_label"]] = label_counts.get(r["score_label"], 0) + 1

    pct = 100 * passed // len(results)
    print("\n" + "=" * 60)
    print(f"  RESULTADO: {passed}/{len(results)} conversas bem-sucedidas  ({pct}%)")
    print(f"  Score medio: {avg:.3f}")
    if blocked:
        print(f"  ATENCAO — BLOCKED_RISK: {blocked} conversas (agent insistente sem resultado)")
    print("\n  Distribuicao por label:")
    for lbl, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        bar = "#" * count
        print(f"    {lbl:<24} {bar} ({count})")
    print("=" * 60)


# ============================================================================
# LOCAL MODE — wraps ConversationEvaluator
# ============================================================================

def run_local_mode(
    scenario_filter: Optional[str],
    profile_filter: Optional[str],
    policy_filter: Optional[str],
    runs_per_scenario: int,
    verbose: bool,
    save_results: bool,
    max_workers: int = 1,
) -> None:
    """Run conversations using the internal DSPy ReceptionistSimulator."""
    from app.core.config import init_dspy
    from app.agents.sdr.gatekeeper.conversation_eval import (
        ConversationEvaluator,
        summarize_results,
    )

    print("Inicializando DSPy...")
    init_dspy()
    print()

    from app.agents.sdr.gatekeeper.receptionist_sim import (
        GATEKEEPER_PROFILES,
        CLINIC_POLICIES,
        SCENARIO_TO_PERSONA,
    )

    evaluator = ConversationEvaluator()

    # Determine which (profile, policy) combos to run
    if scenario_filter and scenario_filter in SCENARIO_TO_PERSONA:
        # Legacy scenario name → single (profile, policy) pair
        profile, policy = SCENARIO_TO_PERSONA[scenario_filter]
        profiles_to_run = [profile]
        policies_to_run = [policy]
        print(f"Cenario '{scenario_filter}' → profile={profile}  policy={policy}\n")
    elif profile_filter or policy_filter:
        profiles_to_run = [profile_filter] if profile_filter else GATEKEEPER_PROFILES
        policies_to_run = [policy_filter]  if policy_filter  else CLINIC_POLICIES
        desc = "/".join(filter(None, [profile_filter, policy_filter]))
        print(f"Filtro: {desc} → {len(profiles_to_run)} profile(s) x {len(policies_to_run)} policy(ies)\n")
    else:
        profiles_to_run = GATEKEEPER_PROFILES
        policies_to_run = CLINIC_POLICIES

    total_combos = len(profiles_to_run) * len(policies_to_run)
    total_runs   = total_combos * runs_per_scenario
    print(f"Rodando {total_combos} combo(s) x {runs_per_scenario} run(s) = {total_runs} conversas\n")

    results = evaluator.run_suite(
        profiles=profiles_to_run,
        policies=policies_to_run,
        runs_per_combo=runs_per_scenario,
        verbose=verbose,
        delay_between_runs=3.0 if max_workers == 1 else 0.0,
        max_workers=max_workers,
    )

    stats = summarize_results(results)

    print("\n" + "=" * 60)
    print(f"  RESULTADO LOCAL: {stats.get('pass_rate_pct', 0):.1f}% aprovacao")
    print(f"  Score medio: {stats.get('avg_score', 0):.3f}")
    print(f"  Turns medios por conversa: {stats.get('avg_agent_turns', 0):.1f}")
    if stats.get("blocking_risk_count"):
        print(f"  ATENCAO — BLOCKED_RISK: {stats['blocking_risk_count']}")

    print("\n  Por profile (score medio):")
    for profile, avg_s in sorted(stats.get("profile_avg_score", {}).items()):
        tag = _score_emoji(avg_s)
        print(f"    [{tag}] {profile:<12} {avg_s:.3f}")

    print("\n  Por policy (score medio):")
    for policy, avg_s in sorted(stats.get("policy_avg_score", {}).items()):
        tag = _score_emoji(avg_s)
        print(f"    [{tag}] {policy:<24} {avg_s:.3f}")
    print("=" * 60)

    if save_results:
        _save_json([r.to_dict() for r in results], tag="local", stats=stats)


# ============================================================================
# WEBHOOK MODE
# ============================================================================

def run_webhook_mode(
    webhook_url: str,
    profile_filter: Optional[str],
    policy_filter: Optional[str],
    all_combos: bool,
    runs: int,
    verbose: bool,
    save_results: bool,
    delay: float,
) -> None:
    """Run conversations using the external webhook receptionist."""
    from app.core.config import init_dspy
    from app.agents.sdr.gatekeeper.agent import GatekeeperAgent

    print("Inicializando DSPy (GatekeeperAgent)...")
    init_dspy()
    gatekeeper = GatekeeperAgent()
    print()

    client = WebhookReceptionistClient(webhook_url)

    # Determine combos to run
    if all_combos:
        combos = [
            (profile, policy)
            for profile in GATEKEEPER_PROFILES
            for policy in CLINIC_POLICIES
        ]
        print(f"Modo: all-combos — {len(combos)} combinacoes x {runs} run(s) = {len(combos)*runs} conversas\n")
    elif profile_filter and policy_filter:
        combos = [(profile_filter, policy_filter)]
        print(f"Modo: especifico — {profile_filter}/{policy_filter} x {runs} run(s)\n")
    elif profile_filter:
        combos = [(profile_filter, pol) for pol in CLINIC_POLICIES]
        print(f"Modo: perfil={profile_filter} — {len(combos)} politicas x {runs} run(s)\n")
    elif policy_filter:
        combos = [(prf, policy_filter) for prf in GATEKEEPER_PROFILES]
        print(f"Modo: policy={policy_filter} — {len(combos)} perfis x {runs} run(s)\n")
    else:
        # Default: single smoke test (helpful/OPEN_TO_PARTNERS = most likely to work)
        combos = [("helpful", "OPEN_TO_PARTNERS")]
        print(f"Modo: smoke test — helpful/OPEN_TO_PARTNERS x {runs} run(s)\n")
        print("Dica: use --all-combos para rodar todas as 25 combinacoes\n")

    all_results: list[dict] = []
    clinic_idx = 0
    total = len(combos) * runs

    for combo_idx, (profile, policy) in enumerate(combos):
        for run_i in range(runs):
            clinic_name = CLINIC_NAMES[clinic_idx % len(CLINIC_NAMES)]
            clinic_idx += 1
            done = combo_idx * runs + run_i + 1

            print(f"[{done:>3}/{total}]  profile={profile:<10}  policy={policy:<22}  {clinic_name}")

            try:
                result = run_webhook_conversation(
                    gatekeeper=gatekeeper,
                    client=client,
                    clinic_name=clinic_name,
                    gatekeeper_profile=profile,
                    clinic_policy=policy,
                    current_hour=datetime.now().hour,
                    verbose=verbose,
                    delay_between_turns=delay,
                )
                all_results.append(result)

                tag   = _score_emoji(result["score"])
                lbl   = result["score_label"]
                sc    = result["score"]
                turns = result["agent_turn_count"]
                secs  = result["duration_ms"] / 1000
                print(f"         [{tag}] {lbl:<24} score={sc:.2f}  turns={turns}  {secs:.1f}s")

            except RuntimeError as e:
                print(f"         [ERRO] {e}")
                all_results.append({
                    "clinic_name":          clinic_name,
                    "gatekeeper_profile":   profile,
                    "clinic_policy":        policy,
                    "final_stage":          "error",
                    "contact_captured":     None,
                    "email_captured":       None,
                    "goodbye_sent":         False,
                    "timed_out":            False,
                    "agent_turn_count":     0,
                    "objection_turn_count": 0,
                    "score":                0.0,
                    "score_label":          "ERROR",
                    "duration_ms":          0.0,
                    "conversation":         [],
                })

            # Cooldown between conversations (except last)
            is_last = done == total
            if not is_last and delay > 0:
                time.sleep(delay)

    # Print matrix (only when multiple combos)
    if len(combos) > 1:
        print_matrix(all_results)

    print_summary(all_results)

    if save_results:
        stats = _compute_stats(all_results)
        _save_json(all_results, tag="webhook", stats=stats)


# ============================================================================
# HELPERS
# ============================================================================

def _compute_stats(results: list) -> dict:
    if not results:
        return {}
    scores  = [r["score"] for r in results]
    avg     = sum(scores) / len(scores)
    passed  = sum(1 for r in results if r["score"] >= 0.70)
    blocked = sum(1 for r in results if r["score_label"] == "BLOCKED_RISK")
    label_counts: dict = {}
    for r in results:
        label_counts[r["score_label"]] = label_counts.get(r["score_label"], 0) + 1
    return {
        "total":               len(results),
        "avg_score":           round(avg, 3),
        "pass_rate_pct":       round(100 * passed / len(results), 1),
        "blocking_risk_count": blocked,
        "label_distribution":  label_counts,
    }


def _save_json(results: list, tag: str, stats: dict) -> None:
    logs_dir = SCRIPT_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = logs_dir / f"{timestamp}_full_conv_{tag}.json"
    payload = {"stats": stats, "results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nResultados salvos: logs/{path.name}")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full multi-turn conversation tests for GatekeeperAgent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Local — combo especifico
  python -m app.agents.sdr.test_full_conversation --local --profile blocker --policy FILTER_FIRST --verbose

  # Local — so um perfil, todas as policies
  python -m app.agents.sdr.test_full_conversation --local --profile helpful --verbose

  # Local — todas as 25 combinacoes
  python -m app.agents.sdr.test_full_conversation --local --verbose

  # Local — cenario legado
  python -m app.agents.sdr.test_full_conversation --local --scenario cooperative --verbose

  # Webhook — smoke test (1 conversa helpful/OPEN_TO_PARTNERS)
  python -m app.agents.sdr.test_full_conversation --webhook http://HOST/webhook/receptionist --verbose

  # Webhook — combo especifico
  python -m app.agents.sdr.test_full_conversation --webhook http://... --profile blocker --policy STRICT_TRIAGE --verbose

  # Webhook — todas as 25 combinacoes, 3 runs cada
  python -m app.agents.sdr.test_full_conversation --webhook http://... --all-combos --runs 3
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--local",
        action="store_true",
        help="Usar ReceptionistSimulator DSPy interno (6 cenarios)",
    )
    mode_group.add_argument(
        "--webhook",
        metavar="URL",
        help="URL do webhook da recepcionista simulada",
    )

    # Local mode options
    parser.add_argument(
        "--scenario",
        metavar="SCENARIO",
        help=(
            "Cenario especifico (local mode): cooperative | ask_data_then_pass | "
            "reverse_contact | email_only | soft_refusal | hard_refusal"
        ),
    )

    # Webhook mode options
    parser.add_argument(
        "--profile",
        metavar="PROFILE",
        choices=GATEKEEPER_PROFILES,
        help="Perfil da recepcionista (local e webhook): " + " | ".join(GATEKEEPER_PROFILES),
    )
    parser.add_argument(
        "--policy",
        metavar="POLICY",
        choices=CLINIC_POLICIES,
        help="Politica da clinica (local e webhook): " + " | ".join(CLINIC_POLICIES),
    )
    parser.add_argument(
        "--all-combos",
        action="store_true",
        help="Rodar todas as 25 combinacoes profile x policy (webhook mode)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="N",
        help="Runs por combinacao (padrao: 1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        metavar="SECS",
        help="Pausa entre turnos em segundos (padrao: 1.5 — respeita rate limits)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Conversas em paralelo (padrao: 1 — sequencial). Recomendado: 3-5 para GPT-4o.",
    )

    # Common
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar transcricao completa de cada conversa",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Nao salvar resultados em JSON",
    )

    args = parser.parse_args()
    save = not args.no_save

    logger = setup_logger("local" if args.local else "webhook")

    print("=" * 60)
    print("  GATEKEEPER — Teste de Conversa Completa")
    if args.local:
        workers_label = f"  paralelo ({args.workers} workers)" if args.workers > 1 else "  sequencial"
        print(f"  Modo: LOCAL (DSPy ReceptionistSimulator) —{workers_label}")
    else:
        print(f"  Modo: WEBHOOK ({args.webhook})")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    try:
        if args.local:
            run_local_mode(
                scenario_filter=args.scenario,
                profile_filter=args.profile,
                policy_filter=args.policy,
                runs_per_scenario=args.runs,
                verbose=args.verbose,
                save_results=save,
                max_workers=args.workers,
            )
        else:
            run_webhook_mode(
                webhook_url=args.webhook,
                profile_filter=args.profile,
                policy_filter=args.policy,
                all_combos=args.all_combos,
                runs=args.runs,
                verbose=args.verbose,
                save_results=save,
                delay=args.delay,
            )
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuario.")
    finally:
        logger.close()


if __name__ == "__main__":
    main()
