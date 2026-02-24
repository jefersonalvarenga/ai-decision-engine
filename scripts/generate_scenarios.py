"""
Generate new test scenarios for an SDR agent using a configurable AI model.

Supports:
  - provider=anthropic  → claude-opus / claude-sonnet (melhor para geração)
  - provider=glm        → glm-5 (gratuito, bom para geração)

Usage:
    python scripts/generate_scenarios.py \
        --agent gatekeeper \
        --count 10 \
        --output-file app/agents/sdr/test_gatekeeper_cases_new.json

Environment variables:
    AI_PROVIDER     anthropic | glm          (default: anthropic)
    AI_MODEL        model name               (default: claude-opus-4-5)
    ANTHROPIC_API_KEY
    GLM_API_KEY
"""

import os
import sys
import json
import argparse
import re
import http.client


# ============================================================================
# AI CLIENT (shared com analyze_failures.py)
# ============================================================================

def call_anthropic(model: str, system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return message.content[0].text


def call_glm(model: str, system: str, user: str) -> str:
    api_key = os.environ["GLM_API_KEY"]
    payload = json.dumps({
        "model": model,
        "temperature": 0.7,
        "max_tokens": 4000,
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
# SCENARIO GENERATION
# ============================================================================

def load_existing_scenarios(agent: str) -> list:
    path = f"app/agents/sdr/test_{agent}_cases.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def load_signature(agent: str) -> str:
    path = f"app/agents/sdr/{agent}/signature.py"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()[:4000]
    return "(signature not found)"


def extract_json_from_response(text: str) -> list:
    """Extract JSON array from AI response, handling markdown code blocks."""
    # Try to find JSON block in markdown
    match = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", text)
    if match:
        return json.loads(match.group(1))

    # Try raw JSON array
    match = re.search(r"(\[[\s\S]+\])", text)
    if match:
        return json.loads(match.group(1))

    raise ValueError("No valid JSON array found in AI response")


def generate(agent: str, count: int, output_file: str):
    provider = os.environ.get("AI_PROVIDER", "anthropic")
    model = os.environ.get("AI_MODEL", "claude-opus-4-5")

    existing = load_existing_scenarios(agent)
    signature = load_signature(agent)

    # Compute current stage distribution for gap analysis
    stage_counts: dict[str, int] = {}
    for s in existing:
        stage = s.get("expected_stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    existing_names = [s["name"] for s in existing]
    existing_sample = json.dumps(existing[:3], ensure_ascii=False, indent=2)

    system_prompt = (
        "Você é um especialista em testes de agentes conversacionais SDR. "
        "Gera cenários de teste realistas, em português brasileiro, para conversas "
        "via WhatsApp entre um SDR e recepcionistas/gestores de clínicas."
    )

    user_prompt = f"""## Agente: {agent.upper()}

## Prompt/Signature atual (primeiros 4000 chars)
```python
{signature}
```

## Distribuição atual de cenários ({len(existing)} total)
{json.dumps(stage_counts, ensure_ascii=False, indent=2)}

## Exemplos do formato existente
```json
{existing_sample}
```

## Cenários já existentes (apenas nomes — não repita)
{chr(10).join(f'- {n}' for n in existing_names)}

## Tarefa
Gere EXATAMENTE {count} cenários de teste NOVOS em JSON.

Priorize cenários que:
1. Cobrem stages com poucos exemplos na distribuição atual
2. Testam edge cases não cobertos (mensagens ambíguas, múltiplos intents, português informal)
3. Testam os smart fallbacks do agent.py (wait signals, max_attempts, response null)
4. Refletem conversas reais de WhatsApp (linguagem informal, abreviações, erros de digitação)

Cada cenário DEVE ter:
- name: string única e descritiva
- clinic_name: string
- conversation_history: array de {{role, content}} (pode ser vazio)
- latest_message: string ou null
- expected_stage: um dos stages válidos do agente
- expected_should_continue: boolean (quando relevante)

Para o gatekeeper os stages válidos são:
opening | requesting | handling_objection | success | failed

Retorne APENAS o JSON array, sem explicações. Exemplo de formato:
```json
[
  {{
    "name": "Recepcionista responde em áudio",
    "clinic_name": "Clínica ABC",
    "conversation_history": [...],
    "latest_message": "[áudio]",
    "expected_stage": "handling_objection",
    "expected_should_continue": true
  }}
]
```
"""

    print(f"🧠 Generating {count} scenarios with {provider}/{model}...")
    response = call_ai(provider, model, system_prompt, user_prompt)

    scenarios = extract_json_from_response(response)
    print(f"✅ Generated {len(scenarios)} scenarios")

    # Validate basic structure
    valid = []
    for s in scenarios:
        if "name" in s and "expected_stage" in s:
            valid.append(s)
        else:
            print(f"⚠️  Skipping invalid scenario: {s.get('name', '(no name)')}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(valid, f, ensure_ascii=False, indent=2)

    print(f"📄 Saved {len(valid)} valid scenarios to {output_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default="gatekeeper")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    generate(args.agent, args.count, args.output_file)


if __name__ == "__main__":
    main()
