"""
analyze_eval_report.py — Envia eval_results.json para GLM-5 e salva análise em markdown.

Lê o JSON estruturado gerado por eval_conversations.py, formata o contexto
completo (scores, conversas, labels) e chama o GLM-5 para diagnóstico e
sugestões concretas de correção na signature/agent.

Uso:
    python scripts/analyze_eval_report.py \
        --eval-json eval_results.json \
        --signature app/agents/sdr/gatekeeper/signature.py \
        --output eval_analysis.md

Env vars:
    GLM_API_KEY     chave ZhipuAI (obrigatório)
    AI_MODEL        modelo a usar (padrão: glm-5)
"""

import os
import sys
import json
import argparse
import http.client
from datetime import datetime


# ============================================================================
# GLM CLIENT
# ============================================================================

def call_glm(model: str, system: str, user: str) -> str:
    api_key = os.environ.get("GLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("GLM_API_KEY não definida")

    payload = json.dumps({
        "model": model,
        "temperature": 0.3,
        "max_tokens": 2500,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    })

    conn = http.client.HTTPSConnection("open.bigmodel.cn")
    conn.request(
        "POST",
        "/api/paas/v4/chat/completions",
        body=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"GLM error: {data['error']}")
    return data["choices"][0]["message"]["content"]


# ============================================================================
# FORMATTERS
# ============================================================================

LABEL_DESC = {
    "SUCCESS":            "✅ Telefone do gestor capturado (≤4 turnos)",
    "SUCCESS_SLOW":       "🐢 Telefone capturado (>4 turnos)",
    "EMAIL_SUCCESS":      "📧 Email do gestor capturado (≤4 turnos)",
    "EMAIL_SUCCESS_SLOW": "🐢📧 Email capturado (>4 turnos)",
    "GRACEFUL_DENIED":    "👋 Encerrou educadamente (≤2 objeções)",
    "SLOW_EXIT":          "⏳ Encerrou mas demorou (3+ objeções)",
    "STUCK":              "🔁 Timeout sem resolução",
    "BLOCKED_RISK":       "🚨 3+ objeções sem captura — risco de bloqueio",
    "UNRESOLVED":         "❓ Sem resolução clara",
    "UNSCORED":           "— Não pontuado",
}


def format_conversation(c: dict) -> str:
    lines = []
    for t in c.get("conversation", []):
        role = "🤖 Sofia" if t["role"] == "agent" else "👤 Recepção"
        stage = f" [{t['stage']}]" if t.get("stage") else ""
        lines.append(f"  {role}{stage}: {t['content']}")
    return "\n".join(lines)


def build_prompt(data: dict, signature_snippet: str) -> str:
    summary = data["summary"]
    conversations = data["conversations"]
    meta = data.get("meta", {})

    # Header
    lines = [
        f"## Resultado do Eval — {meta.get('timestamp', 'N/A')}",
        "",
        f"**Score médio:** {summary['avg_score']} | "
        f"**Taxa aprovação:** {summary['pass_rate_pct']}% | "
        f"**BLOCKED_RISK:** {summary['blocking_risk_count']} | "
        f"**Turnos médios:** {summary['avg_agent_turns']}",
        "",
        "### Score por cenário",
    ]
    for scenario, score in summary.get("scenario_avg_score", {}).items():
        icon = "✅" if score >= 0.70 else ("⚠️" if score >= 0.30 else "❌")
        lines.append(f"- {icon} `{scenario}`: {score}")

    lines += ["", "### Distribuição de labels"]
    for label, count in summary.get("label_distribution", {}).items():
        desc = LABEL_DESC.get(label, label)
        lines.append(f"- `{label}` ({count}x): {desc}")

    # Only include low-score conversations (score < 0.70) to stay within token budget
    low_score = [c for c in conversations if c["score"] < 0.70]
    lines += ["", f"### Conversas com score < 0.70 ({len(low_score)}/{len(conversations)})"]

    for c in low_score:
        lines += [
            "",
            f"#### `{c['scenario']}` — score={c['score']} ({c['score_label']})",
            f"stage_final={c['final_stage']} | goodbye_sent={c['goodbye_sent']} | "
            f"turns={c['agent_turn_count']} | objections={c['objection_turn_count']}",
            "",
            format_conversation(c),
        ]

    lines += [
        "",
        "---",
        "## Signature atual (primeiros 3000 chars)",
        "```python",
        signature_snippet[:3000],
        "```",
    ]

    return "\n".join(lines)


# ============================================================================
# ANALYSIS
# ============================================================================

SYSTEM_PROMPT = """\
Você é um engenheiro sênior especialista em DSPy, agentes conversacionais e SDR.
Analise resultados de avaliação multi-turno do agente Sofia (GatekeeperAgent) \
com objetividade e proponha correções concretas e diretas.
Seja técnico. Foque em causa raiz, não em sintomas.
"""


def analyze(eval_json: str, signature_path: str, output_path: str, model: str) -> None:
    with open(eval_json, encoding="utf-8") as f:
        data = json.load(f)

    signature_snippet = ""
    if os.path.exists(signature_path):
        with open(signature_path, encoding="utf-8") as f:
            signature_snippet = f.read()

    summary = data["summary"]
    avg_score = summary["avg_score"]
    blocking = summary["blocking_risk_count"]
    low_scenarios = [
        s for s, sc in summary.get("scenario_avg_score", {}).items() if sc < 0.70
    ]

    print(f"📊 Score médio: {avg_score} | BLOCKED_RISK: {blocking} | "
          f"Cenários com score < 0.70: {len(low_scenarios)}")

    if avg_score >= 0.85 and blocking == 0:
        msg = "✅ Score acima de 0.85 e sem BLOCKED_RISK — nenhuma correção necessária."
        print(msg)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        return

    context = build_prompt(data, signature_snippet)

    user_prompt = f"""{context}

---

## Tarefa

Analise os resultados acima e responda em markdown estruturado:

### 🔍 Diagnóstico por cenário com score < 0.70
Para cada cenário problemático: causa raiz provável (ambiguidade no prompt,
lógica do agente, comportamento do simulador, etc.)

### 🛠️ Correções sugeridas (priorizadas)
Correções concretas e diretas. Para cada uma, especifique:
- **Onde:** `signature.py` / `agent.py` / `conversation_eval.py`
- **O quê:** trecho atual → trecho corrigido (se aplicável)
- **Por quê:** raciocínio em 1 frase

### 📊 Padrão geral
Existe um padrão entre as falhas? O que indica sobre o agente?

### ✅ Próximos passos
Lista ordenada (máx. 4 itens) das mudanças de maior impacto.

Máximo 700 palavras. Seja direto e técnico.
"""

    print(f"🤖 Chamando {model} para análise...")
    result = call_glm(model, SYSTEM_PROMPT, user_prompt)

    # Cabeçalho do relatório
    header = (
        f"# 🤖 Análise GLM-5 — Eval Conversations\n\n"
        f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}  \n"
        f"**Modelo:** `{model}`  \n"
        f"**Score médio:** {avg_score} | "
        f"**BLOCKED_RISK:** {blocking} | "
        f"**Cenários < 0.70:** {', '.join(low_scenarios) or 'nenhum'}\n\n"
        f"---\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + result)

    print(f"✅ Análise salva em: {output_path}")
    print(f"\n--- Preview ---\n{result[:600]}...\n")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analisa eval_results.json com GLM-5 e salva diagnóstico em markdown"
    )
    parser.add_argument(
        "--eval-json", default="eval_results.json",
        help="Caminho para o JSON gerado por eval_conversations.py (padrão: eval_results.json)"
    )
    parser.add_argument(
        "--signature", default="app/agents/sdr/gatekeeper/signature.py",
        help="Caminho para signature.py (contexto para o GLM)"
    )
    parser.add_argument(
        "--output", default="eval_analysis.md",
        help="Arquivo de saída markdown (padrão: eval_analysis.md)"
    )
    args = parser.parse_args()

    model = os.environ.get("AI_MODEL", "glm-5")

    if not os.path.exists(args.eval_json):
        print(f"❌ Arquivo não encontrado: {args.eval_json}", file=sys.stderr)
        sys.exit(1)

    analyze(args.eval_json, args.signature, args.output, model)


if __name__ == "__main__":
    main()
