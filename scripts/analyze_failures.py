"""
Analyze test failures using a configurable AI model and output markdown.

Supports:
  - provider=anthropic  → claude-haiku / claude-opus via Anthropic SDK
  - provider=glm        → glm-4.7 / glm-5 via ZhipuAI REST API

Usage:
    python scripts/analyze_failures.py \
        --agent gatekeeper \
        --test-log test_output.txt \
        --output analysis.md

Environment variables:
    AI_PROVIDER     anthropic | glm          (default: anthropic)
    AI_MODEL        model name               (default: claude-haiku-4-5)
    ANTHROPIC_API_KEY
    GLM_API_KEY
"""

import os
import sys
import argparse
import json
import re
import http.client
import urllib.parse


# ============================================================================
# AI CLIENT
# ============================================================================

def call_anthropic(model: str, system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return message.content[0].text


def call_glm(model: str, system: str, user: str) -> str:
    api_key = os.environ["GLM_API_KEY"]
    payload = json.dumps({
        "model": model,
        "temperature": 0.4,
        "max_tokens": 2000,
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


def call_ai(provider: str, model: str, system: str, user: str) -> str:
    if provider == "glm":
        return call_glm(model, system, user)
    return call_anthropic(model, system, user)


# ============================================================================
# MAIN
# ============================================================================

def extract_failures(log_content: str) -> list[str]:
    """Extract failure lines from test output."""
    failures = re.findall(r"•\s+((?:GATEKEEPER|CLOSER)\s+\|.+?)(?:\n|$)", log_content)
    return failures


def load_signature(agent: str) -> str:
    """Load the agent's signature/prompt for context."""
    path = f"app/agents/sdr/{agent}/signature.py"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()[:3000]  # limit to avoid token overflow
    return "(signature not found)"


def analyze(agent: str, log_path: str, output_path: str):
    provider = os.environ.get("AI_PROVIDER", "anthropic")
    model = os.environ.get("AI_MODEL", "claude-haiku-4-5")

    with open(log_path, encoding="utf-8") as f:
        log_content = f.read()

    failures = extract_failures(log_content)

    if not failures:
        with open(output_path, "w") as f:
            f.write("Nenhuma falha detectada nos testes.\n")
        print("✅ No failures to analyze.")
        return

    signature_snippet = load_signature(agent)

    system_prompt = (
        "Você é um engenheiro sênior especialista em agentes conversacionais com DSPy. "
        "Analise falhas de testes de forma objetiva e sugira correções concretas."
    )

    user_prompt = f"""## Falhas detectadas nos testes do agente {agent.upper()}

{chr(10).join(f'- {f}' for f in failures)}

## Trecho do prompt/signature atual (primeiros 3000 chars)
```python
{signature_snippet}
```

## Tarefa
Analise cada falha e responda em markdown com:

### 🔍 Diagnóstico por falha
Para cada falha: qual é a causa provável (prompt ambíguo, fallback incorreto, cenário de edge case não coberto, etc.)

### 🛠️ Correções sugeridas
Correções concretas e priorizadas (prompt, fallback, novo cenário de teste)

### 📊 Padrão geral
Existe um padrão entre as falhas? O que isso indica sobre o agente?

Seja direto e técnico. Máximo 500 palavras.
"""

    print(f"🤖 Analyzing {len(failures)} failure(s) with {provider}/{model}...")
    result = call_ai(provider, model, system_prompt, user_prompt)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"✅ Analysis written to {output_path}")
    print(f"\n--- Preview ---\n{result[:500]}...")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default="gatekeeper")
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--output", default="analysis.md")
    args = parser.parse_args()

    analyze(args.agent, args.test_log, args.output)


if __name__ == "__main__":
    main()
