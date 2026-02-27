"""
Conversation Evaluator — Multi-turn conversation runner + scoring.

Orchestrates full conversations between GatekeeperAgent (Sofia) and
ReceptionistSimulator (GLM-4-Flash), then scores outcomes.

Scoring rubric:
  1.0  — Phone captured in ≤ 4 turns                  [SUCCESS]
  0.75 — Phone captured in > 4 turns                  [SUCCESS_SLOW]
  0.85 — Email captured in ≤ 4 turns                  [EMAIL_SUCCESS]
  0.65 — Email captured in > 4 turns                  [EMAIL_SUCCESS_SLOW]
  0.80 — Manager confirmed on channel, ≤ 4 turns      [CHANNEL_SUCCESS]
  0.60 — Manager confirmed on channel, > 4 turns      [CHANNEL_SUCCESS_SLOW]
  0.70 — Graceful exit, ≤ 2 objection turns           [GRACEFUL_DENIED]
  0.30 — Graceful exit, 3+ objection turns            [SLOW_EXIT]
  0.00 — No resolution / timeout                      [STUCK]
 -0.30 — 3+ objections, no contact, risk of blocking  [BLOCKED_RISK]
"""

import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime as _dt
from typing import Optional, Callable, Any

from .receptionist_sim import (
    ReceptionistSimulator,
    ReceptionistScenario,
    GATEKEEPER_PROFILES,
    CLINIC_POLICIES,
    SCENARIO_EXPECTED_OUTCOMES,
    scenario_to_persona,
)
from .agent import GatekeeperAgent


# ============================================================================
# RETRY WITH EXPONENTIAL BACKOFF
# ============================================================================

def _call_with_retry(fn: Callable, *args, max_retries: int = 4, **kwargs) -> Any:
    """
    Call fn(*args, **kwargs) with exponential backoff on rate limit errors.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in str(e) or "rate_limit" in err_str or "ratelimit" in err_str
            is_transient  = "500" in str(e) or "502" in str(e) or "503" in str(e) or "timeout" in err_str

            if (is_rate_limit or is_transient) and attempt < max_retries - 1:
                wait = (10 * (2 ** attempt)) + random.uniform(0, 3)
                print(f"  ⏳ {'Rate limit' if is_rate_limit else 'Transient error'} "
                      f"(attempt {attempt + 1}/{max_retries}), aguardando {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ConversationTurn:
    role:             str           # "agent" (Sofia) | "human" (receptionist)
    content:          str
    stage:            Optional[str] = None    # GatekeeperAgent stage (agent turns only)
    intent_detected:  Optional[str] = None    # receptionist intent (human turns only)
    confidence:       Optional[float] = None  # receptionist confidence (human turns only)
    current_profile:  Optional[str] = None    # receptionist's effective profile
    timestamp:        float = field(default_factory=time.time)


@dataclass
class ConversationResult:
    # Required fields (no defaults) — must come first
    gatekeeper_profile: str   # final profile (may have escalated)
    clinic_policy:      str
    clinic_name:        str
    turns:              list  # list[ConversationTurn]
    final_stage:        str

    # Optional fields (with defaults)
    initial_profile:    str = ""     # profile at start (before escalation)
    contact_captured: Optional[str] = None
    email_captured:   Optional[str] = None
    goodbye_sent:     bool = False
    timed_out:        bool = False

    # Counts
    agent_turn_count:         int = 0
    objection_turn_count:     int = 0
    turns_without_progress:   int = 0

    # Score
    score:       float = 0.0
    score_label: str   = "UNSCORED"

    # Meta
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "initial_profile":        self.initial_profile or self.gatekeeper_profile,
            "gatekeeper_profile":     self.gatekeeper_profile,
            "clinic_policy":          self.clinic_policy,
            "clinic_name":            self.clinic_name,
            "final_stage":            self.final_stage,
            "contact_captured":       self.contact_captured,
            "email_captured":         self.email_captured,
            "goodbye_sent":           self.goodbye_sent,
            "timed_out":              self.timed_out,
            "agent_turn_count":       self.agent_turn_count,
            "objection_turn_count":   self.objection_turn_count,
            "turns_without_progress": self.turns_without_progress,
            "score":                  self.score,
            "score_label":            self.score_label,
            "duration_ms":            round(self.duration_ms, 1),
            "conversation": [
                {
                    "role":            t.role,
                    "content":         t.content,
                    "stage":           t.stage,
                    "intent_detected": t.intent_detected,
                    "confidence":      t.confidence,
                    "current_profile": t.current_profile,
                }
                for t in self.turns
            ],
        }


# ============================================================================
# SCORING
# ============================================================================

def score_conversation(result: ConversationResult) -> tuple:
    """Score a completed conversation. Returns (score, label)."""
    captured_phone  = bool(result.contact_captured)
    captured_email  = bool(result.email_captured)
    graceful_denied = result.final_stage in ("failed", "denied") and result.goodbye_sent
    stuck           = result.timed_out or result.final_stage not in ["success", "failed", "denied"]
    insistent       = result.objection_turn_count > 2

    if insistent and not captured_phone and not captured_email:
        return -0.30, "BLOCKED_RISK"

    if captured_phone:
        return (1.00, "SUCCESS") if result.agent_turn_count <= 4 else (0.75, "SUCCESS_SLOW")

    if captured_email:
        return (0.85, "EMAIL_SUCCESS") if result.agent_turn_count <= 4 else (0.65, "EMAIL_SUCCESS_SLOW")

    # Gestor acompanha mensagens no canal atual — contact do decisor confirmado, sem número/email explícito
    if result.final_stage == "success":
        return (0.80, "CHANNEL_SUCCESS") if result.agent_turn_count <= 4 else (0.60, "CHANNEL_SUCCESS_SLOW")

    if graceful_denied:
        return (0.70, "GRACEFUL_DENIED") if result.objection_turn_count <= 2 else (0.30, "SLOW_EXIT")

    if stuck:
        return 0.00, "STUCK"

    return 0.10, "UNRESOLVED"


# ============================================================================
# CONVERSATION RUNNER
# ============================================================================

class ConversationEvaluator:
    """
    Runs full multi-turn conversations between Sofia (GatekeeperAgent)
    and the ReceptionistSimulator (GLM-4-Flash).
    """

    MAX_TURNS = 10  # Hard safety limit

    def __init__(
        self,
        gatekeeper:   Optional[GatekeeperAgent]    = None,
        receptionist: Optional[ReceptionistSimulator] = None,
    ):
        self.gatekeeper   = gatekeeper   or GatekeeperAgent()
        self.receptionist = receptionist or ReceptionistSimulator()

    def run(
        self,
        gatekeeper_profile: str,
        clinic_policy:      str,
        clinic_name:        str = "Clínica Teste",
        current_hour:       int = 10,
        current_weekday:    Optional[int] = None,
        verbose:            bool = False,
        # Legacy support
        scenario:           Optional[ReceptionistScenario] = None,
    ) -> ConversationResult:
        """
        Run a complete multi-turn conversation.

        Args:
            gatekeeper_profile: blocker | curious | helpful | busy | protocol
            clinic_policy:      FILTER_FIRST | NO_DIRECT_CONTACT | EMAIL_GATE |
                                OPEN_TO_PARTNERS | STRICT_TRIAGE
            clinic_name:        name of the clinic
            current_hour:       hour of day (0-23) for greeting
            verbose:            print each turn to stdout
            scenario:           legacy — if provided, overrides profile/policy

        Returns:
            Scored ConversationResult
        """
        # Legacy scenario → profile/policy
        if scenario is not None:
            gatekeeper_profile, clinic_policy = scenario_to_persona(scenario)

        if current_weekday is None:
            current_weekday = _dt.now().weekday()

        start_time             = time.time()
        history: list          = []
        turns:   list          = []
        agent_turn_count       = 0
        objection_turn_count   = 0
        turns_without_progress = 0
        final_stage            = "opening"
        contact_captured       = None
        email_captured         = None
        goodbye_sent           = False
        timed_out              = False
        initial_profile        = gatekeeper_profile   # capture before escalation

        if verbose:
            print(f"\n  [{clinic_name}]")
            print(f"  {'─'*56}")

        receptionist_ended = False

        for turn_idx in range(self.MAX_TURNS):

            # ── Sofia's turn ──────────────────────────────────────────────
            sofia_result = _call_with_retry(
                self.gatekeeper.forward,
                clinic_name=clinic_name,
                conversation_history=history.copy(),
                latest_message=history[-1]["content"] if history else None,
                current_hour=current_hour,
                current_weekday=current_weekday,
                attempt_count=agent_turn_count,
            )

            stage       = sofia_result["conversation_stage"]
            response    = sofia_result.get("response_message", "")
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
                turns.append(ConversationTurn(
                    role="agent", content=response, stage=stage
                ))
                history.append({"role": "agent", "content": response})
                agent_turn_count += 1
                if verbose:
                    print(f"  Sofia [{stage}]: {response}")

            # Terminal — stop after Sofia's last message
            # Also stop if receptionist already ended (Sofia just sent her closing)
            if stage in ["success", "failed"] or receptionist_ended:
                break

            if not should_send:
                if verbose:
                    print(f"  Sofia aguardando (stage={stage})")

            # ── Receptionist's turn (GLM-4-Flash) ─────────────────────────
            rec_result = _call_with_retry(
                self.receptionist.forward,
                gatekeeper_profile=gatekeeper_profile,
                clinic_policy=clinic_policy,
                clinic_name=clinic_name,
                conversation_history=history.copy(),
                latest_agent_message=response or "(sem mensagem)",
                turn_number=turn_idx + 1,
                turns_without_progress=turns_without_progress,
            )

            rec_response    = rec_result["response"]
            rec_ended       = rec_result["conversation_ended"]
            intent          = rec_result["intent_detected"]
            confidence      = rec_result["confidence"]
            current_profile = rec_result["current_profile"]

            # Update effective profile (may have escalated)
            gatekeeper_profile = current_profile

            # Track turns without progress
            if rec_result.get("contact_provided"):
                turns_without_progress = 0
            else:
                turns_without_progress += 1

            if rec_response:
                turns.append(ConversationTurn(
                    role="human",
                    content=rec_response,
                    intent_detected=intent,
                    confidence=confidence,
                    current_profile=current_profile,
                ))
                history.append({"role": "human", "content": rec_response})

                if verbose:
                    profile_tag = f" [{current_profile}]" if current_profile != initial_profile else ""
                    print(f"  Recepção{profile_tag}: {rec_response}")
                    if intent:
                        print(f"      intent={intent}  confidence={confidence:.2f}  "
                              f"turns_without_progress={turns_without_progress}")

            if rec_ended:
                receptionist_ended = True
                if verbose:
                    print("  [Recepcionista encerrou — aguardando fechamento de Sofia]")

        else:
            timed_out = True
            if verbose:
                print(f"  [Timeout: {self.MAX_TURNS} turnos sem resolução]")

        duration_ms = (time.time() - start_time) * 1000

        result = ConversationResult(
            gatekeeper_profile=gatekeeper_profile,
            initial_profile=initial_profile,
            clinic_policy=clinic_policy,
            clinic_name=clinic_name,
            turns=turns,
            final_stage=final_stage,
            contact_captured=contact_captured,
            email_captured=email_captured,
            goodbye_sent=goodbye_sent,
            timed_out=timed_out,
            agent_turn_count=agent_turn_count,
            objection_turn_count=objection_turn_count,
            turns_without_progress=turns_without_progress,
            duration_ms=duration_ms,
        )

        result.score, result.score_label = score_conversation(result)

        if verbose:
            tag = "OK" if result.score >= 0.7 else ("WARN" if result.score >= 0.3 else "FAIL")
            print(f"\n  [{tag}] score={result.score:.2f} ({result.score_label})  "
                  f"turns={agent_turn_count}  {duration_ms/1000:.1f}s\n")

        return result

    def run_suite(
        self,
        profiles:           Optional[list] = None,
        policies:           Optional[list] = None,
        clinic_names:       Optional[list] = None,
        runs_per_combo:     int = 1,
        verbose:            bool = False,
        delay_between_runs: float = 3.0,
        max_workers:        int = 1,
        # Legacy support
        scenarios:          Optional[list] = None,
        runs_per_scenario:  Optional[int]  = None,
    ) -> list:
        """
        Run multiple conversations across profile × policy combinations.

        Args:
            profiles:           list of profiles to test. Defaults to all 5.
            policies:           list of policies to test. Defaults to all 5.
            clinic_names:       clinic names to rotate.
            runs_per_combo:     how many runs per (profile, policy) pair.
            verbose:            print each conversation turn.
            delay_between_runs: seconds between conversations (rate limit guard).
            scenarios:          legacy — if provided, maps to profile/policy combos.
            runs_per_scenario:  legacy alias for runs_per_combo.

        Returns:
            list[ConversationResult]
        """
        # Legacy: scenarios → profile/policy pairs
        if scenarios is not None:
            combos = [scenario_to_persona(s) for s in scenarios]
        else:
            combos = [
                (profile, policy)
                for profile in (profiles or GATEKEEPER_PROFILES)
                for policy  in (policies or CLINIC_POLICIES)
            ]

        if runs_per_scenario is not None:
            runs_per_combo = runs_per_scenario

        if clinic_names is None:
            clinic_names = [
                "Clínica Bella Vita",
                "Centro Odontológico São Paulo",
                "Clínica Estética Prime",
                "Dermoclínica Saúde",
                "Odonto Express",
                "Clínica Dr. Silva",
                "Instituto de Estética Avançada",
                "Clínica Oral Care",
            ]

        total = len(combos) * runs_per_combo

        # Build flat task list — (task_index, profile, policy, clinic_name)
        tasks = []
        for combo_idx, (profile, policy) in enumerate(combos):
            for run_i in range(runs_per_combo):
                clinic = clinic_names[(combo_idx * runs_per_combo + run_i) % len(clinic_names)]
                tasks.append((len(tasks), profile, policy, clinic))

        # ── PARALLEL MODE ──────────────────────────────────────────────────
        if max_workers > 1:
            if verbose:
                print("  ⚠️  verbose desativado em modo paralelo (output seria intercalado)\n")

            # Pre-warm the receptionist LM singleton in the main thread so
            # parallel workers don't race to initialise it simultaneously.
            from .receptionist_sim import _get_receptionist_lm
            _get_receptionist_lm()

            _lock   = threading.Lock()
            _done   = [0]
            ordered = [None] * total   # preserve original combo order

            def _run_one(task):
                idx, profile, policy, clinic = task
                # Stagger initial burst: spread first wave across 0-2 s
                time.sleep((idx % max_workers) * (2.0 / max(max_workers, 1)))
                result = self.run(
                    gatekeeper_profile=profile,
                    clinic_policy=policy,
                    clinic_name=clinic,
                    verbose=False,
                )
                with _lock:
                    _done[0] += 1
                    done = _done[0]
                    tag  = "OK  " if result.score >= 0.7 else ("WARN" if result.score >= 0.3 else "FAIL")
                    print(f"  [{done:>3}/{total}] [{tag}] {profile:<10} {policy:<22} "
                          f"score={result.score:.2f} ({result.score_label})")
                ordered[idx] = result
                return result

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_run_one, t) for t in tasks]
                for f in as_completed(futures):
                    f.result()   # re-raise any exception from worker

            return ordered

        # ── SEQUENTIAL MODE (default) ──────────────────────────────────────
        results = []
        for done_idx, (task_idx, profile, policy, clinic) in enumerate(tasks, start=1):
            if verbose:
                print(f"\n{'='*60}")
                print(f"[{done_idx}/{total}]  profile={profile}  policy={policy}  clinic={clinic}")
                print('='*60)

            result = self.run(
                gatekeeper_profile=profile,
                clinic_policy=policy,
                clinic_name=clinic,
                verbose=verbose,
            )
            results.append(result)

            if not verbose:
                tag = "OK  " if result.score >= 0.7 else ("WARN" if result.score >= 0.3 else "FAIL")
                print(f"  [{done_idx:>3}/{total}] [{tag}] {profile:<10} {policy:<22} "
                      f"score={result.score:.2f} ({result.score_label})")

            is_last = done_idx == total
            if delay_between_runs > 0 and not is_last:
                if verbose:
                    print(f"  ⏸  Cooldown {delay_between_runs}s...")
                time.sleep(delay_between_runs)

        return results


# ============================================================================
# SUMMARY STATS
# ============================================================================

def summarize_results(results: list) -> dict:
    """Compute aggregate statistics from a list of ConversationResults."""
    if not results:
        return {}

    scores    = [r.score for r in results]
    avg_score = sum(scores) / len(scores)

    label_counts:   dict = {}
    profile_scores: dict = {}
    policy_scores:  dict = {}

    for r in results:
        label_counts[r.score_label] = label_counts.get(r.score_label, 0) + 1
        # Group by initial_profile (not final — which may have escalated)
        initial = r.initial_profile or r.gatekeeper_profile
        profile_scores.setdefault(initial, []).append(r.score)
        policy_scores.setdefault(r.clinic_policy, []).append(r.score)

    profile_avg = {k: round(sum(v) / len(v), 3) for k, v in profile_scores.items()}
    policy_avg  = {k: round(sum(v) / len(v), 3) for k, v in policy_scores.items()}

    pass_rate            = sum(1 for r in results if r.score >= 0.7) / len(results) * 100
    blocking_risk_count  = sum(1 for r in results if r.score_label == "BLOCKED_RISK")
    avg_agent_turns      = sum(r.agent_turn_count for r in results) / len(results)

    return {
        "total":                len(results),
        "avg_score":            round(avg_score, 3),
        "pass_rate_pct":        round(pass_rate, 1),
        "blocking_risk_count":  blocking_risk_count,
        "label_distribution":   label_counts,
        "profile_avg_score":    profile_avg,
        "policy_avg_score":     policy_avg,
        # Legacy key kept for backward compat
        "scenario_avg_score":   profile_avg,
        "avg_agent_turns":      round(avg_agent_turns, 1),
    }


# ============================================================================
# DSPy METRIC (for BootstrapFewShot / MIPROv2)
# ============================================================================

def gatekeeper_conversation_metric(example: dict, prediction: ConversationResult, trace=None) -> float:
    """DSPy metric function for optimizer integration."""
    expected = example.get("expected_outcome", "decisor_captured")
    score    = prediction.score

    if expected == "decisor_captured":
        if prediction.contact_captured or prediction.email_captured:
            score = min(1.0, score + 0.1)
    elif expected == "denied":
        if prediction.final_stage == "denied" and prediction.goodbye_sent:
            score = min(1.0, score + 0.1)

    return score
