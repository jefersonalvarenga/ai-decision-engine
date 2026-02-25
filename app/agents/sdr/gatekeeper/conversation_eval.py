"""
Conversation Evaluator — Multi-turn conversation runner + scoring.

Orchestrates full conversations between GatekeeperAgent (Sofia) and
ReceptionistSimulator, then scores outcomes for DSPy optimization.

Scoring rubric:
  1.0  — Decisor captured (phone) in ≤ 4 turns       [SUCCESS]
  0.85 — Decisor captured (email) in ≤ 4 turns        [EMAIL_SUCCESS]
  0.70 — Graceful denied (goodbye sent, ≤ 2 objections) [GRACEFUL_DENIED]
  0.30 — Graceful denied but too many turns (3+)       [SLOW_EXIT]
  0.00 — No resolution / stuck / timeout               [STUCK]
 -0.30 — Insistent (3+ objection turns, blocking risk) [BLOCKED_RISK]
"""

import time
import random
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime

from .receptionist_sim import ReceptionistSimulator, ReceptionistScenario, SCENARIO_EXPECTED_OUTCOMES
from .agent import GatekeeperAgent


# ============================================================================
# RETRY WITH EXPONENTIAL BACKOFF (handles 429 / rate limit errors)
# ============================================================================

def _call_with_retry(fn: Callable, *args, max_retries: int = 4, **kwargs) -> Any:
    """
    Call fn(*args, **kwargs) with exponential backoff on rate limit errors.
    Handles OpenAI/LiteLLM 429 and transient network errors.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in str(e) or "rate_limit" in err_str or "ratelimit" in err_str
            is_transient = "500" in str(e) or "502" in str(e) or "503" in str(e) or "timeout" in err_str

            if (is_rate_limit or is_transient) and attempt < max_retries - 1:
                # Exponential backoff: 10s, 20s, 40s + jitter
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
    role: str          # "agent" (Sofia) | "human" (receptionist)
    content: str
    stage: Optional[str] = None       # GatekeeperAgent stage for agent turns
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationResult:
    scenario: ReceptionistScenario
    clinic_name: str
    turns: list[ConversationTurn]

    # Final state
    final_stage: str               # success | failed | denied | gathering_decisor
    contact_captured: Optional[str] = None   # phone number if captured
    email_captured: Optional[str] = None     # email if captured
    goodbye_sent: bool = False
    timed_out: bool = False

    # Counts
    agent_turn_count: int = 0
    objection_turn_count: int = 0

    # Score
    score: float = 0.0
    score_label: str = "UNSCORED"

    # Meta
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario.value,
            "clinic_name": self.clinic_name,
            "final_stage": self.final_stage,
            "contact_captured": self.contact_captured,
            "email_captured": self.email_captured,
            "goodbye_sent": self.goodbye_sent,
            "timed_out": self.timed_out,
            "agent_turn_count": self.agent_turn_count,
            "objection_turn_count": self.objection_turn_count,
            "score": self.score,
            "score_label": self.score_label,
            "duration_ms": round(self.duration_ms, 1),
            "conversation": [
                {"role": t.role, "content": t.content, "stage": t.stage}
                for t in self.turns
            ],
        }


# ============================================================================
# SCORING
# ============================================================================

def score_conversation(result: ConversationResult) -> tuple[float, str]:
    """
    Score a completed conversation based on outcome quality.

    Returns (score, label)
    """
    captured_phone = bool(result.contact_captured)
    captured_email = bool(result.email_captured)
    graceful_denied = result.final_stage == "denied" and result.goodbye_sent
    stuck = result.timed_out or result.final_stage not in ["success", "failed", "denied"]
    insistent = result.objection_turn_count > 2

    # Blocking risk penalty overrides everything
    if insistent and not captured_phone and not captured_email:
        return -0.30, "BLOCKED_RISK"

    if captured_phone:
        if result.agent_turn_count <= 4:
            return 1.00, "SUCCESS"
        return 0.75, "SUCCESS_SLOW"

    if captured_email:
        if result.agent_turn_count <= 4:
            return 0.85, "EMAIL_SUCCESS"
        return 0.65, "EMAIL_SUCCESS_SLOW"

    if graceful_denied:
        if result.objection_turn_count <= 2:
            return 0.70, "GRACEFUL_DENIED"
        return 0.30, "SLOW_EXIT"

    if stuck:
        return 0.00, "STUCK"

    return 0.10, "UNRESOLVED"


# ============================================================================
# CONVERSATION RUNNER
# ============================================================================

class ConversationEvaluator:
    """
    Runs full multi-turn conversations between Sofia and the receptionist simulator.
    """

    MAX_TURNS = 10  # Hard safety limit to prevent infinite loops

    def __init__(
        self,
        gatekeeper: Optional[GatekeeperAgent] = None,
        receptionist: Optional[ReceptionistSimulator] = None,
    ):
        self.gatekeeper = gatekeeper or GatekeeperAgent()
        self.receptionist = receptionist or ReceptionistSimulator()

    def run(
        self,
        scenario: ReceptionistScenario,
        clinic_name: str = "Clínica Teste",
        current_hour: int = 10,
        verbose: bool = False,
    ) -> ConversationResult:
        """
        Run a complete multi-turn conversation for the given scenario.

        Returns a scored ConversationResult.
        """
        start_time = time.time()
        history: list[dict] = []
        turns: list[ConversationTurn] = []
        agent_turn_count = 0
        objection_turn_count = 0
        final_stage = "opening"
        contact_captured = None
        email_captured = None
        goodbye_sent = False
        timed_out = False

        for turn_idx in range(self.MAX_TURNS):
            # ---- Sofia's turn ----
            attempt_count = agent_turn_count  # messages already sent

            sofia_result = _call_with_retry(
                self.gatekeeper.forward,
                clinic_name=clinic_name,
                conversation_history=history.copy(),
                latest_message=history[-1]["content"] if history else None,
                current_hour=current_hour,
                attempt_count=attempt_count,
            )

            stage = sofia_result["conversation_stage"]
            final_stage = stage
            response_msg = sofia_result.get("response_message", "")
            should_send = sofia_result.get("should_send_message", False)

            # Track contact capture
            if sofia_result.get("extracted_manager_contact"):
                contact_captured = sofia_result["extracted_manager_contact"]
            if sofia_result.get("extracted_manager_email"):
                email_captured = sofia_result["extracted_manager_email"]

            # Track objection turns (proxy: agent_turn_count > 2)
            if stage == "handling_objection":
                objection_turn_count += 1

            # Track goodbye
            if stage == "failed" and should_send and response_msg:
                goodbye_sent = True

            # Record agent turn
            if response_msg and should_send:
                turns.append(ConversationTurn(role="agent", content=response_msg, stage=stage))
                history.append({"role": "agent", "content": response_msg})
                agent_turn_count += 1

                if verbose:
                    print(f"  🤖 Sofia [{stage}]: {response_msg}")

            # Terminal stage — stop
            if stage in ["success", "failed"]:
                break

            if not should_send:
                # Agent chose not to respond (wait signal or empty)
                if verbose:
                    print(f"  ⏸  Sofia aguardando (should_send=False, stage={stage})")

            # ---- Receptionist's turn ----
            receptionist_result = _call_with_retry(
                self.receptionist.forward,
                scenario=scenario,
                clinic_name=clinic_name,
                conversation_history=history.copy(),
                latest_agent_message=response_msg or "(sem mensagem)",
                turn_number=turn_idx + 1,
            )

            rec_response = receptionist_result["response"]
            rec_ended = receptionist_result["conversation_ended"]

            if rec_response:
                turns.append(ConversationTurn(role="human", content=rec_response))
                history.append({"role": "human", "content": rec_response})

                if verbose:
                    print(f"  👤 Recepção: {rec_response}")

            if rec_ended:
                if verbose:
                    print(f"  🏁 Recepcionista encerrou a conversa")
                break

        else:
            # Exceeded MAX_TURNS
            timed_out = True
            if verbose:
                print(f"  ⏰ Timeout: {self.MAX_TURNS} turnos sem resolução")

        duration_ms = (time.time() - start_time) * 1000

        result = ConversationResult(
            scenario=scenario,
            clinic_name=clinic_name,
            turns=turns,
            final_stage=final_stage,
            contact_captured=contact_captured,
            email_captured=email_captured,
            goodbye_sent=goodbye_sent,
            timed_out=timed_out,
            agent_turn_count=agent_turn_count,
            objection_turn_count=objection_turn_count,
            duration_ms=duration_ms,
        )

        result.score, result.score_label = score_conversation(result)
        return result

    def run_suite(
        self,
        scenarios: Optional[list[ReceptionistScenario]] = None,
        clinic_names: Optional[list[str]] = None,
        runs_per_scenario: int = 1,
        verbose: bool = False,
        delay_between_runs: float = 5.0,
    ) -> list[ConversationResult]:
        """
        Run multiple conversations across all (or selected) scenarios.

        Args:
            scenarios: List of scenarios to run. Defaults to all 6.
            clinic_names: Clinic names to rotate. Defaults to test names.
            runs_per_scenario: How many times to run each scenario (for variance).
            verbose: Print conversation turns.

        Returns:
            List of ConversationResult, one per run.
        """
        if scenarios is None:
            scenarios = list(ReceptionistScenario)

        if clinic_names is None:
            clinic_names = [
                "Clínica Bella Vita",
                "Centro Odontológico São Paulo",
                "Clínica Estética Prime",
                "Dermoclinica Saúde",
                "Odonto Express",
                "Clínica Dr. Silva",
            ]

        results = []
        for i, scenario in enumerate(scenarios):
            for run in range(runs_per_scenario):
                clinic = clinic_names[(i * runs_per_scenario + run) % len(clinic_names)]
                if verbose:
                    print(f"\n{'='*60}")
                    print(f"📋 Cenário: {scenario.value} | Clínica: {clinic} | Run {run+1}/{runs_per_scenario}")
                    print('='*60)

                result = self.run(scenario=scenario, clinic_name=clinic, verbose=verbose)
                results.append(result)

                if verbose:
                    emoji = "✅" if result.score >= 0.7 else ("⚠️" if result.score >= 0.3 else "❌")
                    print(f"\n  {emoji} Score: {result.score:.2f} ({result.score_label}) | {result.agent_turn_count} turns Sofia")

                # Cooldown between conversations to avoid TPM rate limits
                is_last = (i == len(scenarios) - 1) and (run == runs_per_scenario - 1)
                if delay_between_runs > 0 and not is_last:
                    if verbose:
                        print(f"  ⏸  Cooldown {delay_between_runs}s...")
                    time.sleep(delay_between_runs)

        return results


# ============================================================================
# SUMMARY STATS
# ============================================================================

def summarize_results(results: list[ConversationResult]) -> dict:
    """Compute aggregate statistics from a list of conversation results."""
    if not results:
        return {}

    scores = [r.score for r in results]
    avg_score = sum(scores) / len(scores)

    label_counts: dict[str, int] = {}
    scenario_scores: dict[str, list[float]] = {}

    for r in results:
        label_counts[r.score_label] = label_counts.get(r.score_label, 0) + 1
        key = r.scenario.value
        scenario_scores.setdefault(key, []).append(r.score)

    scenario_avg = {k: round(sum(v) / len(v), 3) for k, v in scenario_scores.items()}

    pass_rate = sum(1 for r in results if r.score >= 0.7) / len(results) * 100
    blocking_risk_count = sum(1 for r in results if r.score_label == "BLOCKED_RISK")

    return {
        "total": len(results),
        "avg_score": round(avg_score, 3),
        "pass_rate_pct": round(pass_rate, 1),
        "blocking_risk_count": blocking_risk_count,
        "label_distribution": label_counts,
        "scenario_avg_score": scenario_avg,
        "avg_agent_turns": round(sum(r.agent_turn_count for r in results) / len(results), 1),
    }


# ============================================================================
# DSPy METRIC (for BootstrapFewShot / MIPROv2)
# ============================================================================

def gatekeeper_conversation_metric(example: dict, prediction: ConversationResult, trace=None) -> float:
    """
    DSPy metric function for optimizer integration.

    example: dict with keys: scenario, clinic_name, expected_outcome
    prediction: ConversationResult from ConversationEvaluator.run()
    """
    expected = example.get("expected_outcome", "decisor_captured")
    score = prediction.score

    # Bonus if prediction matches expected outcome category
    if expected == "decisor_captured":
        if prediction.contact_captured or prediction.email_captured:
            score = min(1.0, score + 0.1)
    elif expected == "denied":
        if prediction.final_stage == "denied" and prediction.goodbye_sent:
            score = min(1.0, score + 0.1)

    return score
