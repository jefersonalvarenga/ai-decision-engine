"""
auto_tune_from_real.py — Auto-tuning baseado em conversas reais do gk_discovered_cases.

Lê conversas reais com baixo quality_score ou is_new_pattern=true do Supabase,
e produz:
  1. Novos casos de teste (test_gatekeeper_cases.json)
  2. Patch de signature (signature_patch_real.json) → usado por apply_signature_patch.py

Uso:
    python scripts/auto_tune_from_real.py \\
        --quality-threshold 0.6 \\
        --limit 10 \\
        --output-test-file app/agents/sdr/test_gatekeeper_cases.json \\
        --output-patch signature_patch_real.json

Variáveis de ambiente:
    SUPABASE_URL         https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY service_role key (leitura total)
    GLM_API_KEY          chave da ZhipuAI
"""

import os
import sys
import json
import argparse
import http.client
import urllib.parse
from datetime import datetime, timezone, timedelta


# ============================================================================
# SUPABASE CLIENT
# ============================================================================

def fetch_discovered_cases(
    supabase_url: str,
    service_key: str,
    quality_threshold: float,
    limit: int,
    since_hours: int = 48,
) -> list[dict]:
    """Lê casos recentes com baixo score ou padrão novo do Supabase REST API."""
    parsed = urllib.parse.urlparse(supabase_url)
    host = parsed.netloc
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()

    # Query: quality_score < threshold OR is_new_pattern = true, ordenado por created_at desc
    params = urllib.parse.urlencode({
        "or": f"(quality_score.lt.{quality_threshold},is_new_pattern.eq.true)",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": str(limit),
        "select": "clinic_name,final_stage,quality_score,outcome_label,outcome_reason,"
                  "sofia_did_well,sofia_should_improve,is_new_pattern,"
                  "suggested_scenario_name,full_conversation",
    })

    path = f"/rest/v1/gk_discovered_cases?{params}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    conn = http.client.HTTPSConnection(host)
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()

    if resp.status != 200:
        raise RuntimeError(f"Supabase error {resp.status}: {body}")

    data = json.loads(body)
    print(f"📥 {len(data)} casos encontrados (threshold={quality_threshold}, últimas {since_hours}h)")
    return data


# ============================================================================
# GLM CLIENT
# ============================================================================

def call_glm(system: str, user: str, max_tokens: int = 4000) -> str:
    api_key = os.environ["GLM_API_KEY"]
    payload = json.dumps({
        "model": "glm-5",
        "temperature": 0.4,
        "max_tokens": max_tokens,
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
    body = json.loads(resp.read().decode())
    conn.close()

    if resp.status != 200:
        raise RuntimeError(f"GLM error {resp.status}: {body}")

    return body["choices"][0]["message"]["content"].strip()


def strip_fences(text: str) -> str:
    import re
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ============================================================================
# GERAR CASOS DE TESTE A PARTIR DE CONVERSAS REAIS
# ============================================================================

SYSTEM_GENERATE = """Você é um especialista em testes de agentes SDR para WhatsApp.

Converta a conversa real fornecida em um caso de teste estruturado para o agente Gatekeeper.

O agente (Sofia, SDR da EasyScale) tenta obter o contato do gestor de clínicas médicas.

Retorne SOMENTE um JSON válido (sem markdown) com este formato exato:
{
  "name": "string descritiva do cenário (ex: 'Recepcionista pede email antes de passar contato')",
  "clinic_name": "nome da clínica da conversa",
  "conversation_history": [
    {"role": "agent", "content": "mensagem da Sofia"},
    {"role": "human", "content": "mensagem da recepcionista"}
  ],
  "latest_message": "última mensagem da recepcionista (input para o agente)",
  "expected_stage": "handling_objection | failed | success | requesting",
  "expected_meeting_confirmed": false
}

IMPORTANTE:
- conversation_history deve conter TODOS os turnos EXCETO o último da recepcionista
- latest_message deve ser a ÚLTIMA mensagem da recepcionista
- expected_stage deve refletir o que Sofia DEVERIA fazer a seguir (não o que fez)
- Se Sofia falhou mas deveria ter continuado, use o stage correto para aquele ponto"""


def generate_test_case(case: dict) -> dict | None:
    """Converte um gk_discovered_case em um test case JSON."""
    conversation = case.get("full_conversation", "").strip()
    if not conversation:
        return None

    user_prompt = f"""Conversa real (Sofia falhou — quality_score={case.get('quality_score', '?')}):

{conversation}

Problemas identificados:
{json.dumps(case.get('sofia_should_improve', []), ensure_ascii=False, indent=2)}

Outcome: {case.get('outcome_label', '?')} — {case.get('outcome_reason', '')}

Converta em caso de teste."""

    try:
        raw = call_glm(SYSTEM_GENERATE, user_prompt)
        cleaned = strip_fences(raw)
        test_case = json.loads(cleaned)
        # Tag para rastrear origem
        test_case["_source"] = "auto_tune_from_real"
        test_case["_outcome"] = case.get("outcome_label", "UNSCORED")
        return test_case
    except Exception as e:
        print(f"  ⚠️  Erro ao gerar caso: {e}", file=sys.stderr)
        return None


# ============================================================================
# GERAR PATCH DE SIGNATURE
# ============================================================================

SYSTEM_PATCH = """Você é um especialista em prompts para agentes SDR de WhatsApp.

Analise os problemas reais identificados em conversas com baixo desempenho
e sugira melhorias específicas para a docstring da GatekeeperSignature (classe DSPy).

Retorne SOMENTE um JSON válido (sem markdown):
{
  "rationale": "explicação das mudanças (max 3 frases)",
  "avg_score": 0.0,
  "low_scenarios": ["lista de padrões problemáticos identificados"],
  "new_docstring": "docstring COMPLETA e MELHORADA da GatekeeperSignature (apenas o conteúdo, sem class nem triple-quotes)"
}

REGRAS para new_docstring:
- Preserve TODA a estrutura e seções existentes
- Apenas ADICIONE ou AJUSTE instruções baseado nos problemas encontrados
- Mantenha PT-BR
- Mantenha mensagens de exemplo curtas (< 100 chars)
- NÃO remova exemplos de sucesso existentes"""


def generate_signature_patch(cases: list[dict], current_signature: str) -> dict | None:
    """Gera um patch para a signature baseado nos problemas das conversas reais."""
    all_improvements = []
    for case in cases:
        improvements = case.get("sofia_should_improve", [])
        if isinstance(improvements, list):
            all_improvements.extend(improvements)
        outcome = case.get("outcome_label", "?")
        reason = case.get("outcome_reason", "")
        all_improvements.append(f"[{outcome}] {reason}")

    avg_score = sum(
        float(c.get("quality_score", 0)) for c in cases
    ) / max(len(cases), 1)

    user_prompt = f"""Signature atual do GatekeeperAgent:

{current_signature}

Problemas reais identificados em {len(cases)} conversas (avg_score={avg_score:.2f}):

{chr(10).join(f'- {p}' for p in all_improvements)}

Gere o patch de melhoria."""

    try:
        raw = call_glm(SYSTEM_PATCH, user_prompt, max_tokens=6000)
        cleaned = strip_fences(raw)
        patch = json.loads(cleaned)
        patch["avg_score"] = round(avg_score, 2)
        return patch
    except Exception as e:
        print(f"  ⚠️  Erro ao gerar patch: {e}", file=sys.stderr)
        return None


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Auto-tune from real conversations")
    parser.add_argument("--quality-threshold", type=float, default=0.6,
                        help="Inclui casos com quality_score abaixo deste valor")
    parser.add_argument("--limit", type=int, default=10,
                        help="Máximo de casos a processar")
    parser.add_argument("--since-hours", type=int, default=48,
                        help="Janela de tempo (horas atrás)")
    parser.add_argument("--output-test-file",
                        default="app/agents/sdr/test_gatekeeper_cases.json",
                        help="Arquivo JSON de casos de teste (append)")
    parser.add_argument("--output-patch",
                        default="signature_patch_real.json",
                        help="Arquivo JSON de patch da signature")
    parser.add_argument("--skip-patch", action="store_true",
                        help="Gera apenas casos de teste, não o patch")
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key  = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not supabase_url or not service_key:
        print("❌ SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórias", file=sys.stderr)
        sys.exit(1)

    # 1. Buscar casos
    cases = fetch_discovered_cases(
        supabase_url, service_key,
        args.quality_threshold, args.limit, args.since_hours,
    )

    if not cases:
        print("✅ Nenhum caso abaixo do threshold — nada a fazer.")
        sys.exit(0)

    # 2. Gerar casos de teste
    print(f"\n🔨 Gerando casos de teste ({len(cases)} conversas)...")
    new_test_cases = []
    for i, case in enumerate(cases):
        print(f"  [{i+1}/{len(cases)}] {case.get('clinic_name','?')} — {case.get('outcome_label','?')}")
        tc = generate_test_case(case)
        if tc:
            new_test_cases.append(tc)
            print(f"    ✅ Gerado: {tc.get('name','?')}")

    if new_test_cases:
        with open(args.output_test_file, encoding="utf-8") as f:
            existing = json.load(f)
        existing.extend(new_test_cases)
        with open(args.output_test_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"\n✅ {len(new_test_cases)} casos adicionados → {args.output_test_file}")
    else:
        print("\n⚠️  Nenhum caso de teste gerado.")

    # 3. Gerar patch de signature
    if not args.skip_patch:
        print(f"\n🔧 Gerando patch de signature...")
        sig_path = "app/agents/sdr/gatekeeper/signature.py"
        with open(sig_path, encoding="utf-8") as f:
            current_sig = f.read()

        patch = generate_signature_patch(cases, current_sig)
        if patch:
            with open(args.output_patch, "w", encoding="utf-8") as f:
                json.dump(patch, f, ensure_ascii=False, indent=2)
            print(f"✅ Patch gerado → {args.output_patch}")
            print(f"   avg_score: {patch.get('avg_score')}")
            print(f"   rationale: {patch.get('rationale','')[:120]}")
        else:
            print("⚠️  Patch não gerado.")
            sys.exit(1)

    print("\n🏁 Auto-tune concluído.")


if __name__ == "__main__":
    main()
