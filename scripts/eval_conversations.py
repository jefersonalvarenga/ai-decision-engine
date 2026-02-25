"""
eval_conversations.py — CLI runner for multi-turn conversation evaluation.

Runs GatekeeperAgent (Sofia) against ReceptionistSimulator across 6 receptionist
scenarios, produces structured JSON + markdown summary, and emits GitHub Actions
outputs.

Usage:
    python scripts/eval_conversations.py [options]

    --runs N          Runs per scenario (default: 1). Use 3+ for variance.
    --scenarios ...   Subset of scenarios (default: all 6)
    --output-json     Path for JSON output (default: eval_results.json)
    --output-md       Path for markdown report (default: eval_report.md)
    --verbose         Print each conversation turn to stdout
    --min-avg-score   Minimum avg score for CI pass (default: 0.55)

GitHub Actions outputs (written to $GITHUB_OUTPUT):
    avg_score, pass_rate, blocking_risk_count, avg_agent_turns, label_distribution

Exit codes:
    0  — pass (avg_score >= threshold AND blocking_risk_count == 0)
    1  — fail (below threshold OR BLOCKED_RISK detected)
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone

# Ensure project root is importable regardless of working directory
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.config import init_dspy
from app.agents.sdr.gatekeeper.conversation_eval import (
    ConversationEvaluator,
    ConversationResult,
    summarize_results,
)
from app.agents.sdr.gatekeeper.receptionist_sim import ReceptionistScenario


# ============================================================================
# THRESHOLDS
# ============================================================================

MIN_AVG_SCORE   = 0.55   # Below → CI failure
WARN_AVG_SCORE  = 0.70   # Below → warning only
MAX_BLOCKING    = 0      # Any BLOCKED_RISK → CI failure


# ============================================================================
# DISPLAY HELPERS
# ============================================================================

SCENARIO_EMOJI = {
    "cooperative":        "🤝",
    "ask_data_then_pass": "🔍",
    "reverse_contact":    "🔄",
    "email_only":         "📧",
    "soft_refusal":       "😐",
    "hard_refusal":       "🚫",
}

LABEL_EMOJI = {
    "SUCCESS":            "✅",
    "SUCCESS_SLOW":       "🐢",
    "EMAIL_SUCCESS":      "📧",
    "EMAIL_SUCCESS_SLOW": "🐢📧",
    "GRACEFUL_DENIED":    "👋",
    "SLOW_EXIT":          "⏳",
    "STUCK":              "🔁",
    "BLOCKED_RISK":       "🚨",
    "UNRESOLVED":         "❓",
    "UNSCORED":           "—",
}


def _score_bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score * width)))
    return "█" * filled + "░" * (width - filled)


# ============================================================================
# MARKDOWN REPORT
# ============================================================================

def build_markdown(
    summary: dict,
    results: list[ConversationResult],
    runs: int,
) -> str:
    avg = summary["avg_score"]
    pass_rate = summary["pass_rate_pct"]
    blocking = summary["blocking_risk_count"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if blocking > 0:
        overall_emoji = "🚨"
        overall_status = "BLOQUEIO DETECTADO"
    elif avg >= WARN_AVG_SCORE:
        overall_emoji = "✅"
        overall_status = "Aprovado"
    elif avg >= MIN_AVG_SCORE:
        overall_emoji = "⚠️"
        overall_status = "Atenção"
    else:
        overall_emoji = "❌"
        overall_status = "Reprovado"

    lines = [
        f"## {overall_emoji} Eval Conversations — Gatekeeper (Sofia) — {overall_status}",
        "",
        f"**Data:** {ts}  ",
        f"**Runs por cenário:** {runs}  ",
        f"**Total de conversas:** {summary['total']}",
        "",
        "### 📊 Resumo Geral",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Score médio | **{avg:.3f}** |",
        f"| Taxa de aprovação (score ≥ 0.70) | **{pass_rate:.1f}%** |",
        f"| Turnos médios da Sofia | {summary['avg_agent_turns']} |",
        f"| Risco de bloqueio (BLOCKED\\_RISK) | {'🚨 **' + str(blocking) + '** ← requer ação imediata' if blocking else '✅ 0'} |",
        "",
        "### 🗂️ Score Médio por Cenário",
        "",
        "| Cenário | Score | Barra |",
        "|---------|-------|-------|",
    ]

    for scenario, score in summary["scenario_avg_score"].items():
        emoji = SCENARIO_EMOJI.get(scenario, "•")
        bar = _score_bar(score)
        flag = " ⚠️" if score < WARN_AVG_SCORE and score >= MIN_AVG_SCORE else (" ❌" if score < MIN_AVG_SCORE else "")
        lines.append(f"| {emoji} `{scenario}` | {score:.3f}{flag} | `{bar}` |")

    lines += [
        "",
        "### 🏷️ Distribuição de Labels",
        "",
        "| Label | Count |",
        "|-------|-------|",
    ]
    for label, count in sorted(summary["label_distribution"].items(), key=lambda x: -x[1]):
        emoji = LABEL_EMOJI.get(label, "•")
        lines.append(f"| {emoji} `{label}` | {count} |")

    lines += [
        "",
        "### 💬 Conversas Detalhadas",
        "",
        "> Clique em cada cenário para expandir a conversa completa.",
        "",
    ]

    for r in results:
        emoji = LABEL_EMOJI.get(r.score_label, "•")
        contact_info = ""
        if r.contact_captured:
            contact_info += f" · 📱 `{r.contact_captured}`"
        if r.email_captured:
            contact_info += f" · 📧 `{r.email_captured}`"

        lines.append(
            f"<details><summary>{emoji} <b>{r.scenario.value}</b> — "
            f"{r.clinic_name} — Score {r.score:.2f} ({r.score_label})"
            f"{contact_info}</summary>"
        )
        lines.append("")
        lines.append(
            f"**Turnos Sofia:** {r.agent_turn_count} | "
            f"**Objections:** {r.objection_turn_count} | "
            f"**Stage final:** `{r.final_stage}` | "
            f"**Duração:** {r.duration_ms:.0f} ms"
        )
        lines.append("")
        lines.append("```")
        for turn in r.turns:
            if turn.role == "agent":
                stage_hint = f" [{turn.stage}]" if turn.stage else ""
                lines.append(f"🤖 Sofia{stage_hint}: {turn.content}")
            else:
                lines.append(f"👤 Recepção: {turn.content}")
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines += [
        "---",
        "",
        "#### Rubrica de Pontuação",
        "",
        "| Score | Label | Critério |",
        "|-------|-------|----------|",
        "| 1.00 | SUCCESS | Telefone capturado em ≤ 4 turnos |",
        "| 0.85 | EMAIL_SUCCESS | Email capturado em ≤ 4 turnos |",
        "| 0.75 | SUCCESS_SLOW | Telefone capturado em > 4 turnos |",
        "| 0.70 | GRACEFUL_DENIED | Encerrou educadamente em ≤ 2 objeções |",
        "| 0.65 | EMAIL_SUCCESS_SLOW | Email capturado em > 4 turnos |",
        "| 0.30 | SLOW_EXIT | Encerrou mas com 3+ objeções |",
        "| 0.10 | UNRESOLVED | Sem resolução clara |",
        "| 0.00 | STUCK | Timeout ou sem resolução |",
        "| -0.30 | BLOCKED_RISK | 3+ objeções sem captura — risco de bloqueio |",
    ]

    return "\n".join(lines)


# ============================================================================
# GITHUB ACTIONS OUTPUTS
# ============================================================================

def emit_gha_outputs(summary: dict) -> None:
    """Write key=value pairs to $GITHUB_OUTPUT if running in CI."""
    gha_output = os.environ.get("GITHUB_OUTPUT")
    if not gha_output:
        return
    with open(gha_output, "a", encoding="utf-8") as f:
        f.write(f"avg_score={summary['avg_score']}\n")
        f.write(f"pass_rate={summary['pass_rate_pct']}\n")
        f.write(f"blocking_risk_count={summary['blocking_risk_count']}\n")
        f.write(f"avg_agent_turns={summary['avg_agent_turns']}\n")
        f.write(f"label_distribution={json.dumps(summary['label_distribution'])}\n")
        f.write(f"total_conversations={summary['total']}\n")


# ============================================================================
# CONSOLE SUMMARY
# ============================================================================

def print_summary(summary: dict) -> None:
    avg = summary["avg_score"]
    blocking = summary["blocking_risk_count"]

    print()
    print("=" * 62)
    print("📊  RESULTADO DA AVALIAÇÃO DE CONVERSAS")
    print("=" * 62)
    print(f"  Total de conversas : {summary['total']}")
    print(f"  Score médio        : {avg:.3f}  {_score_bar(avg)}")
    print(f"  Taxa de aprovação  : {summary['pass_rate_pct']:.1f}%")
    print(f"  Turnos médios      : {summary['avg_agent_turns']}")
    print(f"  Risco de bloqueio  : {'🚨 ' + str(blocking) if blocking else '✅ 0'}")
    print()
    print("  Score por cenário:")
    for scenario, score in summary["scenario_avg_score"].items():
        status = "✅" if score >= WARN_AVG_SCORE else ("⚠️ " if score >= MIN_AVG_SCORE else "❌")
        emoji = SCENARIO_EMOJI.get(scenario, " ")
        bar = _score_bar(score, width=8)
        print(f"    {status} {emoji} {scenario:<25} {score:.3f}  {bar}")
    print()
    print("  Distribuição de labels:")
    for label, count in sorted(summary["label_distribution"].items(), key=lambda x: -x[1]):
        le = LABEL_EMOJI.get(label, " ")
        print(f"    {le}  {label:<22} {count}")
    print("=" * 62)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avaliação multi-turno do GatekeeperAgent (Sofia) contra ReceptionistSimulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        metavar="N",
        help="Número de runs por cenário (padrão: 1; use ≥3 para estabilidade estatística)",
    )
    parser.add_argument(
        "--scenarios", nargs="*",
        choices=[s.value for s in ReceptionistScenario],
        default=None,
        metavar="SCENARIO",
        help=f"Cenários a executar (padrão: todos). Opções: {', '.join(s.value for s in ReceptionistScenario)}",
    )
    parser.add_argument(
        "--output-json", default="eval_results.json",
        metavar="FILE",
        help="Arquivo de saída JSON (padrão: eval_results.json)",
    )
    parser.add_argument(
        "--output-md", default="eval_report.md",
        metavar="FILE",
        help="Arquivo de saída Markdown (padrão: eval_report.md)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Imprimir cada turno da conversa durante a execução",
    )
    parser.add_argument(
        "--min-avg-score", type=float, default=MIN_AVG_SCORE,
        metavar="SCORE",
        help=f"Score médio mínimo para CI pass (padrão: {MIN_AVG_SCORE})",
    )
    parser.add_argument(
        "--delay", type=float, default=5.0,
        metavar="SECS",
        help="Delay em segundos entre conversas para evitar TPM rate limit (padrão: 5.0)",
    )
    args = parser.parse_args()

    # ── Configure DSPy LM ─────────────────────────────────────────────────
    init_dspy()

    # ── Resolve scenarios ──────────────────────────────────────────────────
    if args.scenarios:
        scenarios = [ReceptionistScenario(s) for s in args.scenarios]
    else:
        scenarios = list(ReceptionistScenario)

    total_runs = len(scenarios) * args.runs
    print(f"🚀 Avaliação iniciada: {len(scenarios)} cenários × {args.runs} run(s) = {total_runs} conversas")
    print(f"   Cenários: {', '.join(s.value for s in scenarios)}")
    if args.verbose:
        print("   Modo verbose: ativado\n")
    else:
        print()

    # ── Run suite ──────────────────────────────────────────────────────────
    evaluator = ConversationEvaluator()
    results = evaluator.run_suite(
        scenarios=scenarios,
        runs_per_scenario=args.runs,
        verbose=args.verbose,
        delay_between_runs=args.delay,
    )

    summary = summarize_results(results)

    # ── Console summary ────────────────────────────────────────────────────
    print_summary(summary)

    # ── JSON output ────────────────────────────────────────────────────────
    output_data = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runs_per_scenario": args.runs,
            "scenarios": [s.value for s in scenarios],
            "min_avg_score_threshold": args.min_avg_score,
        },
        "summary": summary,
        "conversations": [r.to_dict() for r in results],
    }
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n📄 JSON salvo em: {args.output_json}")

    # ── Markdown report ────────────────────────────────────────────────────
    md_content = build_markdown(summary, results, args.runs)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"📝 Relatório salvo em: {args.output_md}")

    # ── GitHub Actions outputs ─────────────────────────────────────────────
    emit_gha_outputs(summary)

    # ── CI exit decision ───────────────────────────────────────────────────
    blocking = summary["blocking_risk_count"]
    avg = summary["avg_score"]

    print()
    if blocking > MAX_BLOCKING:
        print(f"❌  CI FAIL: {blocking} conversa(s) com BLOCKED_RISK")
        print("    Sofia está sendo insistente — risco real de bloqueio no WhatsApp.")
        sys.exit(1)

    if avg < args.min_avg_score:
        print(f"❌  CI FAIL: Score médio {avg:.3f} abaixo do mínimo {args.min_avg_score:.3f}")
        sys.exit(1)

    if avg < WARN_AVG_SCORE:
        print(f"⚠️   AVISO: Score {avg:.3f} abaixo do ideal ({WARN_AVG_SCORE:.3f})")
        print("    Considere ajustar o prompt (signature.py) ou aumentar MAX_OBJECTION_TURNS.")

    print(f"✅  CI PASS: Score {avg:.3f} ≥ {args.min_avg_score:.3f}, sem BLOCKED_RISK")
    sys.exit(0)


if __name__ == "__main__":
    main()
