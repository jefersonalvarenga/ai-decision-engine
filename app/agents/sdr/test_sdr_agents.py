"""
Testes locais para os agentes SDR (Gatekeeper e Closer)

Execute com:
    python -m app.agents.sdr.test_sdr_agents

Ou para testar cenários específicos:
    python -m app.agents.sdr.test_sdr_agents --gatekeeper
    python -m app.agents.sdr.test_sdr_agents --closer
    python -m app.agents.sdr.test_sdr_agents --interactive
"""

import os
import sys
import time
import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path

# Diretório onde este arquivo está localizado
SCRIPT_DIR = Path(__file__).parent.absolute()

# Adiciona o diretório raiz ao path
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


# ============================================================================
# LOGGER — duplica stdout para arquivo de log
# ============================================================================

class TeeLogger:
    """Escreve simultaneamente no terminal e num arquivo de log."""

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


def setup_logger(agent: str) -> TeeLogger:
    """Cria o diretório de logs e inicia o TeeLogger."""
    from app.core.config import get_settings
    settings = get_settings()
    provider = settings.dspy_provider
    model = settings.dspy_model if settings.dspy_provider != "glm" else "glm-5"

    logs_dir = SCRIPT_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{agent}_{provider}_{model}.log"
    log_path = logs_dir / filename

    logger = TeeLogger(log_path)
    sys.stdout = logger
    print(f"📝 Log salvo em: logs/{filename}\n")
    return logger

from app.core.config import init_dspy


# ============================================================================
# JUDGE — avalia automaticamente se a resposta segue a estratégia
# ============================================================================

# Estratégia resumida para o juiz (não o prompt completo — só o fluxo principal)
_GATEKEEPER_STRATEGY = """
Você avalia se a Iris (agente SDR da EasyScale) respondeu corretamente a uma recepcionista de clínica.

ESTRATÉGIA CORRETA DA IRIS:
1. PRIMEIRA MSG (opening): Confirmar se é a clínica → "Bom dia, é da clínica X?"
2. CLÍNICA CONFIRMOU (requesting): Pedir gestor → "Gostaria de falar com o gestor ou gestora"
3. PERGUNTAM ASSUNTO 1ª vez (handling_objection): Resposta MÍNIMA → "Seria sobre assunto comercial"
   ⚠️ SEMPRE "Seria sobre assunto comercial" na 1ª vez — NUNCA pitch, NUNCA "atendimento da clínica"
3b. INSISTEM 2ª vez (após "assunto comercial" já foi dito): Resposta mínima → "É sobre atendimento da clínica."
    ⚠️ NÃO dar pitch da empresa na 2ª vez — manter resposta curta
3c. BLOQUEIAM 3ª vez (sem progresso): Pivotar → "Qual o email do gestor então?" ou "Qual o canal pra tratar disso?"
4. DÃO CONTATO (success): Agradecer e encerrar → "Obrigado!"
FAILED: após 3 handling_objection sem progresso, ou rejeição definitiva ("já disse que não", etc.)

SITUAÇÕES DE SUCCESS (reconheça corretamente):
- Qualquer número com 8+ dígitos = success (mesmo WhatsApp geral ou número compartilhado)
- Qualquer email com @ = success
- "A gestora acompanha as mensagens aqui" / "Pode falar por esse número que ela vê" = success
  → Resposta correta: "Obrigado!" e encerrar. NÃO peça outro contato.
- "[contato compartilhado: Nome | +55...]" = success imediato

SITUAÇÕES DE HANDLING_OBJECTION (NÃO é failed):
- "Não estamos precisando de novidades" / "No momento não temos interesse" (1ª vez) = handling_objection
  → Resposta: "Entendo. É uma parceria rápida, posso mandar o contato dele?"
- "Ele não está agora, retorne amanhã" = handling_objection
  → Resposta: "Combinado. Tem o contato direto dele para eu adiantar?" (WhatsApp OU email — qualquer canal ok)
- "Não aceitamos abordagem por texto. Liga no fixo" = handling_objection
  → Resposta: "Entendo! Tem o email do gestor para eu enviar algo?" (não WhatsApp — rejeitaram texto)
- Número com apenas 4 dígitos = INCOMPLETO → handling_objection correto pedir número completo

QUANDO PERGUNTAM "COM QUEM FALO?" / "QUAL SEU NOME?":
- Resposta correta: nome + próximo passo → "Aqui é [nome]. Gostaria de falar com o gestor."
- NÃO aceite só o nome sem o próximo passo

QUANDO PERGUNTAM "QUAL A EMPRESA?":
- Pode revelar: "EasyScale" (apenas o nome, não o produto)

OPORTUNIDADES (NÃO são objection — são avanço):
- "Pode falar comigo mesmo" / "Sou eu quem cuida disso" / "Sou eu mesmo o gestor"
  → Stage = requesting. Resposta: "Ótimo! Seria sobre assunto comercial. Qual o seu WhatsApp?"
  → NÃO classifique como handling_objection.

CASOS ESPECIAIS:
- "Qual gestor?" / "Qual gestor exatamente?" → resposta correta = "Seria sobre assunto comercial" (NÃO "administração ou financeiro")
- "Me fala o nome da empresa" → resposta correta = "EasyScale" + stage = handling_objection (NÃO requesting)
- "Pode mandar uma apresentação?" → resposta correta = "É uma parceria rápida, posso mandar o contato dele?" (NÃO pedir WhatsApp direto)
- "Que gestor?! Sem interesse!" (tom agressivo, 1ª vez) → resposta correta = "Seria sobre assunto comercial"
- Quando attempt_count ≥ 3 E última msg ainda bloqueia → stage correto = failed
- "Tente mês que vem" após 2+ objeções → failed (não continue tentando)

MENSAGEM DE FAILED (aceite como correto):
- Stage = failed → mensagem de encerramento educada com despedida contextual É CORRETA.
- Exemplos aceitos: "Quando precisarem de X, pode me chamar. Bom trabalho!" / "Entendido, desculpe o incômodo. Boa tarde!"
- NÃO penalize por incluir despedida contextual ou frase de "porta aberta" — isso é a estratégia esperada.
- Só penalize se o agente continuar vendendo ou insistindo após encerrar.

PERSONAS ESPECIAIS (comportamento diferente do fluxo normal):

MENU BOT (stage=requesting):
- Detectado quando a clínica responde com menu numerado/estruturado ("escolha uma opção", "1. Agendar", etc.)
- Resposta CORRETA: qualquer abordagem que tente chegar em um humano — "2", "falar com atendente", número da opção, etc.
- Se o bot já repetiu o mesmo menu após tentativas anteriores visíveis no histórico → stage=menu_blocked é CORRETO.
- NÃO penalize variações de bypass (ex: "2" em vez de "falar com atendente") — o objetivo é chegar no humano.

WAITING (stage=requesting, should_send_message=false):
- Detectado quando a clínica responde com sinal de espera ("aguarde", "um momento", "já te atendo", etc.)
- Resposta CORRETA: NÃO enviar nada (response_message vazio, should_send_message=false).
- NÃO penalize silêncio aqui — é a estratégia correta aguardar o próximo turno.

ERROS COMUNS A DETECTAR:
- Dar pitch da EasyScale na 1ª objeção/pergunta (deveria ser só "assunto comercial" primeiro)
- Usar "É sobre atendimento da clínica" quando "assunto comercial" ainda não foi dito (ordem errada)
- Usar Proposta Irrecusável (frases longas com R$5 mil) antes de dizer "assunto comercial"
- Especificar "administração ou financeiro" quando perguntam "qual gestor?" (deve ser "assunto comercial")
- Pular etapas (ex: já dar email na 1ª objeção quando a recepção não bloqueou)
- Não encerrar quando deveria (success/failed com should_continue=true incorreto)
- Mensagem muito longa (>100 chars) para um canal WhatsApp — EXCETO frases da seção Proposta Irrecusável
- Tratar "Pode falar comigo mesmo" como objection (é oportunidade!)
- Pedir outro contato quando "gestora acompanha esse WhatsApp" — o canal atual JÁ é o contato
- Continuar tentando quando attempt_count ≥ 3 e há resistência clara (deve ir para failed)
"""

import dspy as _dspy


class _JudgeSignature(_dspy.Signature):
    """Avalia se a resposta do agente SDR está correta para a situação."""
    strategy:        str = _dspy.InputField(desc="Estratégia esperada do agente")
    conversation:    str = _dspy.InputField(desc="Histórico completo da conversa (turnos anteriores)")
    latest_message:  str = _dspy.InputField(desc="Última mensagem recebida da recepção")
    agent_response:  str = _dspy.InputField(desc="Resposta que o agente gerou")
    expected_stage:  str = _dspy.InputField(desc="Stage esperado para essa situação")
    actual_stage:    str = _dspy.InputField(desc="Stage que o agente classificou")

    is_valid: str = _dspy.OutputField(
        desc="'true' se a resposta está correta e segue a estratégia, 'false' caso contrário"
    )
    reason: str = _dspy.OutputField(
        desc="Explicação de 1-2 frases: por que está certo ou qual erro foi cometido"
    )


_judge = None      # lazy init — usa o LM do SDR sendo testado
_judge_lm = None   # LM fixo para o juiz — sempre GPT-4o (independente do SDR)


def _init_judge_lm():
    """
    Inicializa o LM fixo do juiz com GPT-4o (sempre, independente do SDR testado).
    Garante avaliações consistentes entre benchmarks de modelos diferentes.
    """
    global _judge_lm
    if _judge_lm is not None:
        return
    try:
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            from app.core.config import get_settings
            openai_key = get_settings().openai_api_key
        if openai_key:
            _judge_lm = _dspy.LM(
                model="openai/gpt-4o",
                api_key=openai_key,
                temperature=0.0,
                max_tokens=300,
            )
            print("⚖️  Juiz LLM  : GPT-4o (fixo, independente do modelo SDR)")
        else:
            print("⚠️  Juiz LLM  : sem OPENAI_API_KEY — usando mesmo LM do SDR")
    except Exception as e:
        print(f"⚠️  Juiz LLM  : falha ao inicializar GPT-4o ({e}) — usando mesmo LM do SDR")


def judge_gatekeeper_response(scenario: dict, result: dict) -> dict:
    """
    Avalia se a resposta do agente está correta usando GPT-4o como juiz fixo.
    Retorna {"valid": bool, "reason": str}
    """
    global _judge
    if _judge is None:
        _judge = _dspy.Predict(_JudgeSignature)

    history = scenario.get("conversation_history", [])
    conv_text = "\n".join(
        f"{'Iris' if t['role'] == 'agent' else 'Recepção'}: {t['content']}"
        for t in history
    ) or "(primeira mensagem — sem histórico)"

    latest = scenario.get("latest_message") or "null (primeira mensagem)"

    try:
        # Usa GPT-4o como juiz se disponível, senão usa o LM padrão do SDR
        if _judge_lm is not None:
            with _dspy.context(lm=_judge_lm):
                verdict = _judge(
                    strategy=_GATEKEEPER_STRATEGY.strip(),
                    conversation=conv_text,
                    latest_message=str(latest),
                    agent_response=result.get("response_message", ""),
                    expected_stage=scenario.get("expected_stage", "?"),
                    actual_stage=result.get("conversation_stage", "?"),
                )
        else:
            verdict = _judge(
                strategy=_GATEKEEPER_STRATEGY.strip(),
                conversation=conv_text,
                latest_message=str(latest),
                agent_response=result.get("response_message", ""),
                expected_stage=scenario.get("expected_stage", "?"),
                actual_stage=result.get("conversation_stage", "?"),
            )
        is_valid = str(verdict.is_valid).strip().lower() == "true"
        reason   = str(verdict.reason).strip()
    except Exception as e:
        is_valid = False
        reason   = f"Erro ao chamar juiz: {e}"

    return {"valid": is_valid, "reason": reason}


# ============================================================================
# TEST SCENARIOS - MENU BOT
# ============================================================================

MENU_BOT_JSON = SCRIPT_DIR / "test_menu_bot_cases.json"
if MENU_BOT_JSON.exists():
    with open(MENU_BOT_JSON, 'r', encoding='utf-8') as f:
        MENU_BOT_SCENARIOS = json.load(f)
else:
    MENU_BOT_SCENARIOS = []


def run_menu_bot_test(scenario: Dict, verbose: bool = True) -> dict:
    """Executa um cenário de teste do MenuBotAgent via gatekeeper_graph."""
    from app.agents.sdr.gatekeeper.graph import gatekeeper_graph

    idx      = scenario.get("_idx", "?")
    expected_stage = scenario.get("expected_stage", "?")
    resolved = "✓ resolved" if scenario.get("resolved") else "⏳ pending"

    print(f"\n{'='*60}")
    print(f"[#{idx}] {scenario['name']}")
    print(f"  Clínica   : {scenario['clinic_name']}")
    print(f"  Esperado  : stage={expected_stage}")
    print(f"  {resolved}")
    print(f"{'='*60}")

    history = scenario.get("conversation_history", [])
    if verbose and history:
        print("\n  Histórico:")
        for turn in history:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"    {prefix} [{turn.get('stage', '')}] {turn['content'][:80]}")

    latest = scenario.get("latest_message", "")
    print(f"  Última msg: {repr(latest[:80])}")

    result = gatekeeper_graph.invoke({
        "clinic_name": scenario["clinic_name"],
        "sdr_name": scenario.get("sdr_name", "Vera"),
        "conversation_history": history,
        "latest_message": latest,
        "current_hour": 10,
        "detected_persona": scenario.get("detected_persona"),
        "persona_confidence": scenario.get("persona_confidence"),
    })

    stage_ok = result["conversation_stage"] == expected_stage
    send_ok  = result["should_send_message"] == scenario.get("expected_should_send", True)

    print(f"\n  {'✅' if stage_ok else '❌'} Stage      : {result['conversation_stage']}  (esperado: {expected_stage})")
    print(f"  {'✅' if send_ok else '❌'} Envia?     : {result['should_send_message']}  (esperado: {scenario.get('expected_should_send', True)})")
    print(f"  📨 Resposta : {repr(result['response_message'])}")
    if result.get("reasoning"):
        print(f"  🧠 Reasoning: {result['reasoning']}")

    return result


# ============================================================================
# TEST SCENARIOS - PERSONA DETECTOR
# ============================================================================

PERSONA_DETECTOR_JSON = SCRIPT_DIR / "test_persona_detector_cases.json"
if PERSONA_DETECTOR_JSON.exists():
    with open(PERSONA_DETECTOR_JSON, 'r', encoding='utf-8') as f:
        PERSONA_DETECTOR_SCENARIOS = json.load(f)
else:
    PERSONA_DETECTOR_SCENARIOS = []


def run_persona_detector_test(scenario: Dict, verbose: bool = True) -> dict:
    """Executa um cenário de teste do PersonaDetector — sem juiz LLM, avaliação categórica."""
    from app.agents.sdr.gatekeeper.persona_detector import PersonaDetector

    idx      = scenario.get("_idx", "?")
    expected = scenario.get("expected_persona", "?")
    resolved = "✓ resolved" if scenario.get("resolved") else "⏳ pending"

    print(f"\n{'='*60}")
    print(f"[#{idx}] {scenario['name']}")
    print(f"  Clínica   : {scenario['clinic_name']}")
    print(f"  Esperado  : {expected}   |   {resolved}")
    print(f"{'='*60}")

    history = scenario.get("conversation_history", [])
    if verbose and history:
        print("\n  Histórico:")
        for turn in history:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"    {prefix} {turn['content'][:80]}")

    latest = scenario.get("latest_message", "")
    print(f"  Última msg: {repr(latest[:80]) if latest else 'null'}")

    detector = PersonaDetector()
    result = detector.forward(
        clinic_name=scenario["clinic_name"],
        conversation_history=history,
        latest_message=latest,
    )

    persona_ok   = result["persona"] == expected
    persona_icon = "✅" if persona_ok else "❌"

    print(f"\n  {persona_icon} Persona    : {result['persona']}  (esperado: {expected})")
    print(f"  📊 Confiança : {result['confidence']}")
    print(f"  🔑 Sinal     : {result['key_signal'][:100]}")
    print(f"  💭 Reasoning : {result['reasoning'][:150]}")

    return result


# ============================================================================
# TEST SCENARIOS - GATEKEEPER
# ============================================================================

# Carregando do arquivo externo (usando caminho absoluto)
GATEKEEPER_JSON = SCRIPT_DIR / "test_gatekeeper_cases.json"
if GATEKEEPER_JSON.exists():
    with open(GATEKEEPER_JSON, 'r', encoding='utf-8') as f:
        GATEKEEPER_SCENARIOS = json.load(f)
else:
    # Fallback: cenários inline se arquivo não existir
    GATEKEEPER_SCENARIOS = [
        {
            "name": "Primeira mensagem",
            "clinic_name": "Clínica Bella Luna",
            "conversation_history": [],
            "latest_message": None,
            "expected_stage": "opening",
        },
    ]




# ============================================================================
# TEST SCENARIOS - CLOSER
# ============================================================================

def get_available_slots() -> List[str]:
    """Gera slots disponíveis para os próximos 3 dias"""
    slots = []
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for day_offset in range(1, 4):
        day = base + timedelta(days=day_offset)
        for hour in [9, 10, 11, 14, 15, 16, 17]:
            slots.append(day.strftime(f"%Y-%m-%d {hour:02d}:00"))
            slots.append(day.strftime(f"%Y-%m-%d {hour:02d}:30"))

    return slots

# Carregando do arquivo externo (usando caminho absoluto)
CLOSER_JSON = SCRIPT_DIR / "test_closer_cases.json"
if CLOSER_JSON.exists():
    with open(CLOSER_JSON, 'r', encoding='utf-8') as f:
        CLOSER_SCENARIOS = json.load(f)
else:
    # Fallback: cenários inline se arquivo não existir
    CLOSER_SCENARIOS = [
        {
            "name": "Primeira mensagem ao gestor",
            "manager_name": "Dr. Carlos",
            "manager_phone": "11999887766",
            "clinic_name": "Clínica Bella Luna",
            "clinic_specialty": "estética",
            "conversation_history": [],
            "latest_message": None,
            "expected_stage": "greeting",
        },
    ]


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_gatekeeper_test(scenario: Dict, verbose: bool = True):
    """Executa um cenário de teste do Gatekeeper"""
    from app.agents.sdr.gatekeeper import gatekeeper_graph

    idx      = scenario.get("_idx", "?")
    expected = scenario.get("expected_stage", "?")
    resolved = "✓ resolved" if scenario.get("resolved") else "⏳ pending"

    print(f"\n{'='*60}")
    print(f"[#{idx}] {scenario['name']}")
    print(f"  Clínica   : {scenario['clinic_name']}")
    print(f"  Esperado  : {expected}   |   {resolved}")
    print(f"{'='*60}")

    history = scenario.get("conversation_history", [])
    if verbose and history:
        print("\n  Histórico:")
        for turn in history:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"    {prefix} {turn['content']}")
    elif not history:
        print("\n  Histórico: (vazio — primeira mensagem)")

    latest = scenario.get("latest_message")
    print(f"  Última msg: {repr(latest) if latest else 'null (primeira mensagem)'}")

    # Conta tentativas (permite override para testar fallback de max attempts)
    attempt_count = scenario.get("attempt_count_override", len([
        t for t in history if t["role"] == "agent"
    ]))

    # Invoca o grafo
    result = gatekeeper_graph.invoke({
        "clinic_name": scenario["clinic_name"],
        "sdr_name": scenario.get("sdr_name", "Vera"),
        "conversation_history": history,
        "latest_message": latest,
        "current_hour": datetime.now().hour,
        "attempt_count": attempt_count,
        "detected_persona": scenario.get("detected_persona"),
        "persona_confidence": scenario.get("persona_confidence"),
    })

    stage_ok = result['conversation_stage'] == expected
    stage_icon = "✅" if stage_ok else "❌"

    print(f"\n  📤 Resposta  : \"{result['response_message']}\"")
    print(f"  {stage_icon} Stage       : {result['conversation_stage']}  (esperado: {expected})")
    print(f"  📞 Contato   : {result.get('extracted_manager_contact') or '—'}")
    print(f"  🙍 Nome      : {result.get('extracted_manager_name') or '—'}")
    print(f"  📨 Envia?    : {result['should_send_message']}")
    print(f"\n  💭 Reasoning : {result['reasoning']}")

    return result


def run_closer_test(scenario: Dict, verbose: bool = True):
    """Executa um cenário de teste do Closer"""
    from app.agents.sdr.closer import closer_graph

    print(f"\n{'='*60}")
    print(f"CLOSER: {scenario['name']}")
    print(f"{'='*60}")

    if verbose and scenario.get("conversation_history"):
        print("\nHistórico:")
        for turn in scenario["conversation_history"]:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"  {prefix} {turn['content']}")

    if scenario.get("latest_message"):
        print(f"\nÚltima msg recebida: \"{scenario['latest_message']}\"")

    # Conta tentativas (permite override para testar fallback 4 — max attempts)
    attempt_count = scenario.get("attempt_count_override", len([
        t for t in scenario.get("conversation_history", [])
        if t["role"] == "agent"
    ]))

    # Gera slots disponíveis (permite override do cenário para testar edge cases)
    available_slots = scenario.get("available_slots_override", get_available_slots())

    # Invoca o grafo
    result = closer_graph.invoke({
        "manager_name": scenario["manager_name"],
        "manager_phone": scenario["manager_phone"],
        "clinic_name": scenario["clinic_name"],
        "clinic_specialty": scenario.get("clinic_specialty", "saúde"),
        "conversation_history": scenario.get("conversation_history", []),
        "latest_message": scenario.get("latest_message"),
        "available_slots": available_slots,
        "current_hour": scenario.get("current_hour_override", datetime.now().hour),
        "attempt_count": attempt_count,
    })

    print(f"\n📤 Resposta do agente:")

    # Trata múltiplas mensagens
    messages = result["response_message"].split("|||")
    for i, msg in enumerate(messages, 1):
        if len(messages) > 1:
            print(f"   Mensagem {i}: \"{msg.strip()}\"")
        else:
            print(f"   Mensagem: \"{msg.strip()}\"")

    print(f"   Stage: {result['conversation_stage']}")
    print(f"   Reunião confirmada: {result['meeting_confirmed']}")
    if result.get("meeting_datetime"):
        print(f"   Data/hora: {result['meeting_datetime']}")
    print(f"   Enviar msg: {result['should_send_message']}")
    print(f"\n💭 Reasoning: {result['reasoning']}")

    # Verifica expectativa
    if scenario.get("expected_stage"):
        expected = scenario["expected_stage"]
        actual = result["conversation_stage"]
        status = "✅" if actual == expected else "⚠️"
        print(f"\n{status} Stage esperado: {expected}, obtido: {actual}")

    return result


def run_interactive_gatekeeper():
    """Modo interativo para testar Gatekeeper"""
    from app.agents.sdr.gatekeeper import gatekeeper_graph

    print("\n" + "="*60)
    print("MODO INTERATIVO - GATEKEEPER")
    print("="*60)

    clinic_name = input("\nNome da clínica: ").strip() or "Clínica Teste"
    conversation_history = []
    detected_persona = None  # persiste entre turnos

    print(f"\nIniciando conversa com {clinic_name}...")
    print("(Digite 'sair' para encerrar)\n")

    while True:
        # Conta tentativas
        attempt_count = len([t for t in conversation_history if t["role"] == "agent"])

        # Se primeira mensagem ou após resposta humana
        latest_message = None
        if conversation_history and conversation_history[-1]["role"] == "human":
            latest_message = conversation_history[-1]["content"]

        # Invoca agente — repassa detected_persona para evitar re-classificação
        result = gatekeeper_graph.invoke({
            "clinic_name": clinic_name,
            "conversation_history": conversation_history,
            "latest_message": latest_message,
            "current_hour": datetime.now().hour,
            "attempt_count": attempt_count,
            "detected_persona": detected_persona,
        })

        # Persiste persona detectada para o próximo turno
        if result.get("detected_persona"):
            detected_persona = result["detected_persona"]

        print(f"🤖 Agente: {result['response_message']}")
        print(f"   [Stage: {result['conversation_stage']}  |  Persona: {detected_persona or 'unknown'}]")

        if result.get("extracted_manager_contact"):
            print(f"   ✅ Contato extraído: {result['extracted_manager_contact']}")

        # Adiciona ao histórico
        conversation_history.append({
            "role": "agent",
            "content": result["response_message"]
        })

        # Verifica se acabou
        if not result["should_send_message"] or result["conversation_stage"] in ["success", "failed"]:
            print("\n[Conversa encerrada]")
            break

        # Input do usuário (simula recepção)
        user_input = input("\n👤 Recepção: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "sair":
            break

        conversation_history.append({
            "role": "human",
            "content": user_input
        })


def run_interactive_closer():
    """Modo interativo para testar Closer"""
    from app.agents.sdr.closer import closer_graph

    print("\n" + "="*60)
    print("MODO INTERATIVO - CLOSER")
    print("="*60)

    manager_name = input("\nNome do gestor (ex: Dr. Carlos): ").strip() or "Dr. Teste"
    clinic_name = input("Nome da clínica: ").strip() or "Clínica Teste"
    specialty = input("Especialidade (odonto/estética/etc): ").strip() or "saúde"

    conversation_history = []
    available_slots = get_available_slots()

    print(f"\nIniciando conversa com {manager_name} da {clinic_name}...")
    print("(Digite 'sair' para encerrar)\n")

    while True:
        # Conta tentativas
        attempt_count = len([t for t in conversation_history if t["role"] == "agent"])

        # Se primeira mensagem ou após resposta humana
        latest_message = None
        if conversation_history and conversation_history[-1]["role"] == "human":
            latest_message = conversation_history[-1]["content"]

        # Invoca agente
        result = closer_graph.invoke({
            "manager_name": manager_name,
            "manager_phone": "11999999999",
            "clinic_name": clinic_name,
            "clinic_specialty": specialty,
            "conversation_history": conversation_history,
            "latest_message": latest_message,
            "available_slots": available_slots,
            "current_hour": datetime.now().hour,
            "attempt_count": attempt_count,
        })

        # Mostra mensagens (pode ter múltiplas)
        messages = result["response_message"].split("|||")
        for msg in messages:
            print(f"🤖 Agente: {msg.strip()}")
            conversation_history.append({
                "role": "agent",
                "content": msg.strip()
            })

        print(f"   [Stage: {result['conversation_stage']}]")

        if result.get("meeting_confirmed"):
            print(f"   ✅ Reunião agendada: {result['meeting_datetime']}")

        # Verifica se acabou
        if not result["should_send_message"] or result["conversation_stage"] in ["scheduled", "lost"]:
            print("\n[Conversa encerrada]")
            break

        # Input do usuário (simula gestor)
        user_input = input("\n👤 Gestor: ").strip()
        if user_input.lower() == "sair":
            break

        conversation_history.append({
            "role": "human",
            "content": user_input
        })


# ============================================================================
# MAIN
# ============================================================================

def mark_resolved(json_path: Path, scenario_name: str, passed: bool, notes: str = "", response: str = "", stage: str = ""):
    """Atualiza resolved + last_run + last_response + last_stage no JSON após cada teste."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cases = json.load(f)
        for c in cases:
            if c.get("name") == scenario_name:
                if passed:
                    c["resolved"] = True
                c["last_run"] = datetime.now().strftime("%Y-%m-%d")
                if notes:
                    c["notes"] = notes
                if response:
                    c["last_response"] = response
                if stage:
                    c["last_stage"] = stage
                break
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Não foi possível salvar resolved: {e}")


def main():
    parser = argparse.ArgumentParser(description="Testes dos agentes SDR")
    parser.add_argument("--gatekeeper", action="store_true", help="Rodar cenários do Gatekeeper")
    parser.add_argument("--persona-detector", action="store_true", help="Rodar cenários do PersonaDetector")
    parser.add_argument("--menu-bot", action="store_true", help="Rodar cenários do MenuBotAgent")
    parser.add_argument("--closer", action="store_true", help="Rodar cenários do Closer")
    parser.add_argument("--interactive", action="store_true", help="Modo interativo")
    parser.add_argument("--all", action="store_true", help="Rodar todos os cenários")
    parser.add_argument(
        "--n", type=int, default=None, metavar="N",
        help="Limitar a N casos pendentes (ex: --n 1 para rodar só o próximo)"
    )
    parser.add_argument(
        "--pending", action="store_true", default=True,
        help="Rodar apenas casos com resolved=false (padrão)"
    )
    parser.add_argument(
        "--all-cases", action="store_true",
        help="Rodar TODOS os casos incluindo resolved=true"
    )
    parser.add_argument(
        "--case", type=int, default=None, metavar="IDX",
        help="Rodar apenas o caso com índice IDX (independente de resolved). Ex: --case 3"
    )

    args = parser.parse_args()

    # Se nenhum argumento, mostra ajuda
    if not any([args.gatekeeper, args.persona_detector, args.menu_bot, args.closer, args.interactive, args.all]):
        parser.print_help()
        print("\nExemplos:")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper          # próximos pendentes")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper --n 1    # só 1 caso pendente")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper --n 5    # próximos 5 pendentes")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases  # todos (incl. resolved)")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper --case 3 # roda caso #3 direto")
        print("  python -m app.agents.sdr.test_sdr_agents --interactive")
        return

    # Inicializa DSPy (modelo SDR) + juiz GPT-4o (fixo)
    print("Inicializando DSPy...")
    init_dspy()
    _init_judge_lm()
    print("DSPy inicializado!\n")

    # Modo interativo — sem log (é interativo, não faz sentido)
    if args.interactive:
        print("\nEscolha o agente:")
        print("1. Gatekeeper (coletar contato)")
        print("2. Closer (agendar reunião)")
        choice = input("\nOpção (1/2): ").strip()

        if choice == "1":
            run_interactive_gatekeeper()
        elif choice == "2":
            run_interactive_closer()
        else:
            print("Opção inválida")
        return

    # Determina qual agente para nomear o log
    agent_label = "all"
    if args.gatekeeper and not args.closer and not args.persona_detector:
        agent_label = "gatekeeper"
    elif args.closer and not args.gatekeeper and not args.persona_detector:
        agent_label = "closer"
    elif args.persona_detector and not args.gatekeeper and not args.closer:
        agent_label = "persona-detector"
    elif args.menu_bot and not args.gatekeeper and not args.closer and not args.persona_detector:
        agent_label = "menu-bot"

    # Inicia logger (após init_dspy para ter settings disponível)
    logger = setup_logger(agent_label)

    # Contadores globais de pass/fail
    total_passed = 0
    total_failed = 0
    failures = []

    # Cenários Gatekeeper
    if args.gatekeeper or args.all:
        print("\n" + "#"*60)
        print("# TESTES GATEKEEPER")
        print("#"*60)

        # Filtra por resolved e aplica --n / --case — preserva índice original do JSON
        total_gk = len(GATEKEEPER_SCENARIOS)
        resolved_gk = sum(1 for s in GATEKEEPER_SCENARIOS if s.get("resolved", False))
        pending_gk = total_gk - resolved_gk
        print(f"\n📊 Status: {resolved_gk}/{total_gk} resolved | {pending_gk} pendentes")

        if args.case is not None:
            # --case N: roda exatamente o caso pelo índice, independente de resolved
            if args.case < 0 or args.case >= total_gk:
                print(f"❌ --case {args.case} fora do intervalo (0–{total_gk - 1})")
                return
            queue = [{**GATEKEEPER_SCENARIOS[args.case], "_idx": args.case}]
            print(f"🎯 Rodando caso #{args.case}: {queue[0]['name']}")
        else:
            only_pending = not args.all_cases
            queue = [
                {**s, "_idx": i}
                for i, s in enumerate(GATEKEEPER_SCENARIOS)
                if not (only_pending and s.get("resolved", False))
            ]
            if args.n:
                queue = queue[:args.n]
                print(f"🎯 Rodando {len(queue)} caso(s) (--n {args.n})")
            else:
                print(f"🎯 Rodando {len(queue)} caso(s) {'pendentes' if only_pending else 'no total'}")

        g_passed = g_failed = 0
        for i_q, scenario in enumerate(queue):
            # Delay entre casos para evitar rate limit (exceto no primeiro)
            if i_q > 0:
                time.sleep(4)
            try:
                result = run_gatekeeper_test(scenario)
                scenario_ok = True
                fail_reasons = []

                # Check 1: Stage classification
                expected = scenario.get("expected_stage")
                actual = result["conversation_stage"]
                if expected and actual != expected:
                    scenario_ok = False
                    fail_reasons.append(f"stage: esperado={expected}, obtido={actual}")

                # Check 2: should_send_message (if annotated)
                if "expected_should_continue" in scenario:
                    if result.get("should_send_message") != scenario["expected_should_continue"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"should_send_message: esperado={scenario['expected_should_continue']}, "
                            f"obtido={result.get('should_send_message')}"
                        )

                # Check 3: juiz LLM — valida qualidade da resposta automaticamente
                verdict = judge_gatekeeper_response(scenario, result)
                judge_icon = "✅" if verdict["valid"] else "❌"
                print(f"  {judge_icon} Juiz LLM   : {verdict['reason']}")
                if not verdict["valid"]:
                    scenario_ok = False
                    fail_reasons.append(f"juiz: {verdict['reason']}")

                last_response = result.get("response_message", "")
                last_stage = result.get("conversation_stage", "")
                if scenario_ok:
                    g_passed += 1
                    print(f"  ✅ PASSOU — marcando resolved=true")
                    mark_resolved(GATEKEEPER_JSON, scenario["name"], passed=True, response=last_response, stage=last_stage)
                else:
                    g_failed += 1
                    reason_str = " | ".join(fail_reasons)
                    failures.append(f"GATEKEEPER | {scenario['name']} | {reason_str}")
                    mark_resolved(GATEKEEPER_JSON, scenario["name"], passed=False, notes=reason_str, response=last_response, stage=last_stage)
            except Exception as e:
                g_failed += 1
                failures.append(f"GATEKEEPER | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")
                mark_resolved(GATEKEEPER_JSON, scenario["name"], passed=False, notes=str(e))

        total_passed += g_passed
        total_failed += g_failed
        total_g = g_passed + g_failed
        print(f"\n{'='*60}")
        print(f"GATEKEEPER: {g_passed}/{total_g} ({100*g_passed//total_g if total_g else 0}%)")
        print(f"{'='*60}")

    # Cenários MenuBot
    if args.menu_bot or args.all:
        print("\n" + "#"*60)
        print("# TESTES MENU BOT")
        print("#"*60)

        total_mb = len(MENU_BOT_SCENARIOS)
        resolved_mb = sum(1 for s in MENU_BOT_SCENARIOS if s.get("resolved", False))
        pending_mb = total_mb - resolved_mb
        print(f"\n📊 Status: {resolved_mb}/{total_mb} resolved | {pending_mb} pendentes")

        only_pending = not args.all_cases
        mb_queue = [
            {**s, "_idx": i}
            for i, s in enumerate(MENU_BOT_SCENARIOS)
            if not (only_pending and s.get("resolved", False))
        ]
        if args.n:
            mb_queue = mb_queue[:args.n]
        print(f"🎯 Rodando {len(mb_queue)} caso(s) {'pendentes' if only_pending else 'no total'}")

        mb_passed = mb_failed = 0
        for i_q, scenario in enumerate(mb_queue):
            try:
                result = run_menu_bot_test(scenario)

                stage_ok = result["conversation_stage"] == scenario.get("expected_stage")
                send_ok  = result["should_send_message"] == scenario.get("expected_should_send", True)

                judge_ok = True
                judge_reason = ""
                if stage_ok and send_ok and result.get("response_message") and scenario.get("expected_response"):
                    judge_result = judge_gatekeeper_response(scenario=scenario, result=result)
                    judge_ok = judge_result.get("valid", True)
                    judge_reason = judge_result.get("reason", "")
                    print(f"  {'✅' if judge_ok else '❌'} Juiz       : {judge_reason}")

                scenario_ok = stage_ok and send_ok and judge_ok

                fail_reasons = []
                if not stage_ok:
                    fail_reasons.append(f"stage: esperado={scenario.get('expected_stage')}, obtido={result['conversation_stage']}")
                if not send_ok:
                    fail_reasons.append(f"should_send: esperado={scenario.get('expected_should_send')}, obtido={result['should_send_message']}")
                if not judge_ok:
                    fail_reasons.append(f"juiz: {judge_reason}")

                if scenario_ok:
                    mb_passed += 1
                    print(f"  ✅ PASSOU — marcando resolved=true")
                    mark_resolved(MENU_BOT_JSON, scenario["name"], passed=True, stage=result["conversation_stage"])
                else:
                    mb_failed += 1
                    reason_str = " | ".join(fail_reasons)
                    failures.append(f"MENU BOT | {scenario['name']} | {reason_str}")
                    print(f"  ❌ FALHOU — {reason_str}")
                    mark_resolved(MENU_BOT_JSON, scenario["name"], passed=False, notes=reason_str, stage=result["conversation_stage"])
            except Exception as e:
                mb_failed += 1
                failures.append(f"MENU BOT | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")
                mark_resolved(MENU_BOT_JSON, scenario["name"], passed=False, notes=str(e))

        total_passed += mb_passed
        total_failed += mb_failed
        total_mb_run = mb_passed + mb_failed
        print(f"\n{'='*60}")
        print(f"MENU BOT: {mb_passed}/{total_mb_run} ({100*mb_passed//total_mb_run if total_mb_run else 0}%)")
        print(f"{'='*60}")

    # Cenários PersonaDetector
    if args.persona_detector or args.all:
        print("\n" + "#"*60)
        print("# TESTES PERSONA DETECTOR")
        print("#"*60)

        total_pd = len(PERSONA_DETECTOR_SCENARIOS)
        resolved_pd = sum(1 for s in PERSONA_DETECTOR_SCENARIOS if s.get("resolved", False))
        pending_pd = total_pd - resolved_pd
        print(f"\n📊 Status: {resolved_pd}/{total_pd} resolved | {pending_pd} pendentes")

        only_pending = not args.all_cases
        pd_queue = [
            {**s, "_idx": i}
            for i, s in enumerate(PERSONA_DETECTOR_SCENARIOS)
            if not (only_pending and s.get("resolved", False))
        ]
        if args.n:
            pd_queue = pd_queue[:args.n]
        print(f"🎯 Rodando {len(pd_queue)} caso(s) {'pendentes' if only_pending else 'no total'}")

        pd_passed = pd_failed = 0
        for i_q, scenario in enumerate(pd_queue):
            if i_q > 0:
                time.sleep(2)
            try:
                result = run_persona_detector_test(scenario)
                expected = scenario.get("expected_persona")
                actual = result["persona"]
                scenario_ok = actual == expected

                if scenario_ok:
                    pd_passed += 1
                    print(f"  ✅ PASSOU — marcando resolved=true")
                    mark_resolved(PERSONA_DETECTOR_JSON, scenario["name"], passed=True, stage=actual)
                else:
                    pd_failed += 1
                    reason = f"persona: esperado={expected}, obtido={actual} (confiança={result['confidence']})"
                    failures.append(f"PERSONA DETECTOR | {scenario['name']} | {reason}")
                    print(f"  ❌ FALHOU — {reason}")
                    mark_resolved(PERSONA_DETECTOR_JSON, scenario["name"], passed=False, notes=reason, stage=actual)
            except Exception as e:
                pd_failed += 1
                failures.append(f"PERSONA DETECTOR | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")
                mark_resolved(PERSONA_DETECTOR_JSON, scenario["name"], passed=False, notes=str(e))

        total_passed += pd_passed
        total_failed += pd_failed
        total_pd_run = pd_passed + pd_failed
        print(f"\n{'='*60}")
        print(f"PERSONA DETECTOR: {pd_passed}/{total_pd_run} ({100*pd_passed//total_pd_run if total_pd_run else 0}%)")
        print(f"{'='*60}")

    # Cenários Closer
    if args.closer or args.all:
        print("\n" + "#"*60)
        print("# TESTES CLOSER")
        print("#"*60)

        c_passed = c_failed = 0
        for scenario in CLOSER_SCENARIOS:
            try:
                result = run_closer_test(scenario)
                expected = scenario.get("expected_stage")
                actual = result["conversation_stage"]
                scenario_ok = True
                fail_reasons = []

                # Check 1: Stage classification
                if expected and actual != expected:
                    scenario_ok = False
                    fail_reasons.append(f"stage: esperado={expected}, obtido={actual}")

                # Check 2: meeting_confirmed (if annotated)
                if "expected_meeting_confirmed" in scenario:
                    if result.get("meeting_confirmed") != scenario["expected_meeting_confirmed"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"meeting_confirmed: esperado={scenario['expected_meeting_confirmed']}, "
                            f"obtido={result.get('meeting_confirmed')}"
                        )

                # Check 3: should_send_message (if annotated)
                if "expected_should_continue" in scenario:
                    if result.get("should_send_message") != scenario["expected_should_continue"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"should_send_message: esperado={scenario['expected_should_continue']}, "
                            f"obtido={result.get('should_send_message')}"
                        )

                # Check 4: meeting_datetime ISO format (if annotated)
                if scenario.get("expected_datetime_format") == "iso":
                    dt_val = result.get("meeting_datetime")
                    if not dt_val:
                        scenario_ok = False
                        fail_reasons.append("meeting_datetime: esperado ISO, obtido=None")
                    else:
                        try:
                            datetime.fromisoformat(dt_val)
                        except (ValueError, TypeError):
                            scenario_ok = False
                            fail_reasons.append(f"meeting_datetime: formato inválido '{dt_val}'")

                if scenario_ok:
                    c_passed += 1
                else:
                    c_failed += 1
                    reason_str = " | ".join(fail_reasons)
                    failures.append(f"CLOSER | {scenario['name']} | {reason_str}")
            except Exception as e:
                c_failed += 1
                failures.append(f"CLOSER | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

        total_passed += c_passed
        total_failed += c_failed
        total_c = c_passed + c_failed
        print(f"\n{'='*60}")
        print(f"CLOSER: {c_passed}/{total_c} ({100*c_passed//total_c if total_c else 0}%)")
        print(f"{'='*60}")

    # Sumário final
    total = total_passed + total_failed
    pct = 100 * total_passed // total if total else 0
    print(f"\n{'='*60}")
    print(f"RESULTADO FINAL: {total_passed}/{total} ({pct}%)")
    if failures:
        print(f"\n⚠️  FALHAS ({len(failures)}):")
        for f in failures:
            print(f"   • {f}")
    else:
        print("✅ Todos os cenários passaram!")
    print(f"{'='*60}")
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    logger.close()


if __name__ == "__main__":
    main()
