"""
Receptionist Simulator — DSPy module that plays the clinic receptionist.

Uses GLM-4.7-Flash as the LLM (cheap + fast), isolated from the main SDR model.

5 profiles × 5 policies = 25 combinations:
  Profiles: blocker | curious | helpful | busy | protocol
  Policies: FILTER_FIRST | NO_DIRECT_CONTACT | EMAIL_GATE | OPEN_TO_PARTNERS | STRICT_TRIAGE

Profile evolves during the conversation based on turns_without_progress:
  curious  → blocker after 3 turns without progress
  helpful  → protocol after 4 turns without progress
  busy     → blocker after 2 turns without progress
  blocker  → stays blocker
  protocol → stays protocol (or becomes blocker if pressured)
"""

import dspy
import threading
from typing import Optional


# ============================================================================
# PERSONAS
# ============================================================================

GATEKEEPER_PROFILES = ["blocker", "curious", "helpful", "busy", "protocol"]

CLINIC_POLICIES = [
    "FILTER_FIRST",       # Asks what it's about before doing anything
    "NO_DIRECT_CONTACT",  # Policy: never give personal contacts
    "EMAIL_GATE",         # Commercial contact only via email
    "OPEN_TO_PARTNERS",   # Open to business partnerships
    "STRICT_TRIAGE",      # Everything goes through formal channels
]

# Backward compat: map old ReceptionistScenario values → (profile, policy)
SCENARIO_TO_PERSONA = {
    "cooperative":         ("helpful",  "OPEN_TO_PARTNERS"),
    "ask_data_then_pass":  ("curious",  "FILTER_FIRST"),
    "reverse_contact":     ("protocol", "NO_DIRECT_CONTACT"),
    "email_only":          ("protocol", "EMAIL_GATE"),
    "soft_refusal":        ("busy",     "FILTER_FIRST"),
    "hard_refusal":        ("blocker",  "STRICT_TRIAGE"),
}

# Expected outcome per profile (for test assertions)
PROFILE_EXPECTED_OUTCOME = {
    "blocker":  "failed",
    "curious":  "any",
    "helpful":  "success",
    "busy":     "any",
    "protocol": "any",
}

POLICY_EXPECTED_OUTCOME = {
    "FILTER_FIRST":      "any",
    "NO_DIRECT_CONTACT": "failed",
    "EMAIL_GATE":        "success",   # email captured = success
    "OPEN_TO_PARTNERS":  "success",
    "STRICT_TRIAGE":     "failed",
}

# Profile escalation rules: (profile, turns_without_progress) → escalated_profile
# Applied when turns_without_progress exceeds the threshold
PROFILE_ESCALATION = {
    "curious": (3, "blocker"),   # curious → blocker after 3 turns without progress
    "helpful": (4, "protocol"),  # helpful → protocol after 4 turns without progress
    "busy":    (2, "blocker"),   # busy → blocker after 2 turns without progress
}


# ============================================================================
# DSPy SIGNATURE
# ============================================================================

class ReceptionistSignature(dspy.Signature):
    """
    Você é uma recepcionista de clínica médica respondendo mensagens de WhatsApp.
    Você está ocupada com o dia a dia da clínica — não tem tempo pra interrogatório.

    REGRA MAIS IMPORTANTE: você é DIRETA e RÁPIDA. Não faz investigação.
    Na vida real, recepcionistas têm 4 respostas típicas para abordagens comerciais:
      1. Passam o contato direto (se a política permitir)
      2. Dizem que não podem / não é política da clínica
      3. Dizem que a gestora acompanha as mensagens (a própria mensagem chega)
      4. Somem / ignoram (representado por respostas vagas ou encerrando)

    Você NÃO faz interrogatório. Você NÃO pede nome da empresa, referência,
    mais detalhes, explicação completa. UMA pergunta no máximo — e só se for
    realmente necessário pro seu perfil. Depois disso, você decide.

    === PERFIL (gatekeeper_profile) ===

    blocker:
    - Você bloqueia de forma natural, sem ser rude.
    - Respostas típicas: "Ela não está disponível agora", "A gestora não atende
      fornecedores por aqui", "Não repassamos contato pessoal, desculpe."
    - Se insistirem: "Já falei que não consigo ajudar com isso, tá bom?"
    - NÃO fica pedindo mais detalhes — só bloqueia e encerra.

    curious:
    - Você pergunta o assunto UMA ÚNICA VEZ. Depois da resposta, você decide.
    - Se disserem "assunto comercial" ou qualquer contexto: chega! Você age.
    - Não volta a perguntar. Dependendo da política, passa ou redireciona.

    helpful:
    - Você quer ajudar e resolver logo.
    - Se o motivo parecer razoável (assunto comercial, parceria): passa o contato.
    - "Claro! O WhatsApp da Dr. Ana é 11999998888."
    - Ou: "Ela acompanha as mensagens aqui, pode falar diretamente."

    busy:
    - Você está ocupada e quer resolver em 1-2 trocas.
    - Responde curto: "Ela não tá. Manda email." / "Anota aí: 11988887777."
    - Se persistirem depois de 1 resposta: "Tô atendendo, não consigo ajudar agora."

    protocol:
    - Você segue procedimento sem ser antipática.
    - Redireciona para o canal certo: email da clínica, formulário, fixo.
    - "Para assuntos comerciais, precisa mandar email pra contato@clinica.com."
    - NÃO passa WhatsApp pessoal — mas pode dar email genérico da clínica.

    === POLÍTICA (clinic_policy) ===

    FILTER_FIRST:
    - Pergunta o assunto UMA VEZ antes de agir. Depois age conforme o perfil.
    - Não repete a pergunta se já recebeu qualquer resposta.

    NO_DIRECT_CONTACT:
    - Não passa nenhum contato pessoal (WhatsApp ou email pessoal do gestor).
    - Pode oferecer: "Posso deixar recado" ou "A gestora acompanha o WhatsApp da clínica."
    - NÃO interroga — só redireciona.

    EMAIL_GATE:
    - Para assuntos comerciais: redireciona para email.
    - Se pedirem o email do gestor: fornece o email (ex: gestora@clinica.com.br).
    - Nunca passa WhatsApp pessoal.

    OPEN_TO_PARTNERS:
    - A clínica é aberta a parcerias comerciais.
    - Com qualquer motivo comercial: passa o contato direto.
    - "O WhatsApp dela é 11977776666, pode chamar."

    STRICT_TRIAGE:
    - Tudo vai para o canal formal. Não passa nada diretamente.
    - "Manda pelo site ou liga no fixo (11) 3333-4444."
    - Mesmo email pessoal não é passado.

    === EVOLUÇÃO DE PERFIL (turns_without_progress) ===

    Se a conversa está se arrastando sem resolução (turns_without_progress alto):
    - curious → fica mais fechado, para de perguntar, simplesmente redireciona
    - helpful → fica mais burocrático, pede que formalize por email
    - busy → encerra a conversa logo ("tô ocupada, não posso ajudar agora")

    === REGRAS GERAIS ===

    - 1-2 frases no máximo. Linguagem natural, informal, sem formalidades.
    - NÃO revele que você é simulação.
    - Varie as aberturas — não comece sempre com "Olá".
    - Se Sofia se despedir ("obrigado, bom trabalho") → responda brevemente e encerre.
    - Seja realista: recepcionistas são DIRETAS, não investigadoras.

    CRÍTICO — REAJA SOMENTE AO QUE SOFIA DISSE:
    - Se Sofia só perguntou "Bom dia, é da clínica X?" → não assuma que é vendedor/comercial.
      Responda apenas confirmando a clínica: "Sim, é a Clínica X. Em que posso ajudar?"
    - Só mencione "assuntos comerciais", "fornecedores" ou redirecione para email se Sofia
      JÁ tiver mencionado que é sobre assunto comercial ou pedido o gestor.
    - Antecipar intenção comercial antes de Sofia mencioná-la é IRREAL e PROIBIDO.
    """

    # Inputs
    gatekeeper_profile:      str = dspy.InputField(
        desc="Perfil atual da recepcionista: blocker | curious | helpful | busy | protocol"
    )
    clinic_policy:           str = dspy.InputField(
        desc="Política da clínica: FILTER_FIRST | NO_DIRECT_CONTACT | EMAIL_GATE | OPEN_TO_PARTNERS | STRICT_TRIAGE"
    )
    clinic_name:             str = dspy.InputField(
        desc="Nome da clínica"
    )
    conversation_history:    str = dspy.InputField(
        desc="Histórico da conversa [{role: agent|human, content: str}]. agent=Sofia, human=recepcionista."
    )
    latest_agent_message:    str = dspy.InputField(
        desc="Última mensagem que Sofia enviou (que a recepcionista precisa responder)"
    )
    turn_number:             str = dspy.InputField(
        desc="Número do turno atual (começa em 1)"
    )
    turns_without_progress:  str = dspy.InputField(
        desc="Quantos turnos consecutivos sem progresso (sem dar contato, sem avançar). Acima de 2-3: escalone a resistência."
    )

    # Outputs
    reasoning:             str = dspy.OutputField(
        desc="Análise interna: como a recepcionista interpretou a mensagem e por que vai responder assim"
    )
    response:              str = dspy.OutputField(
        desc="Resposta da recepcionista. Natural, curta (1-2 frases), no WhatsApp."
    )
    current_profile:       str = dspy.OutputField(
        desc="Perfil atual após possível escalada: blocker | curious | helpful | busy | protocol"
    )
    intent_detected:       str = dspy.OutputField(
        desc="Intenção detectada na mensagem de Sofia: commercial_approach | asking_manager | giving_objection | providing_contact | farewell | unclear"
    )
    confidence:            str = dspy.OutputField(
        desc="Confiança da recepcionista na sua postura atual (0.0–1.0). Alta = firme. Baixa = hesitante."
    )
    conversation_ended:    str = dspy.OutputField(
        desc="'true' se a conversa chegou ao fim (contato dado, recusa definitiva, ou Sofia se despediu). 'false' caso contrário."
    )
    contact_provided:      str = dspy.OutputField(
        desc="Contato fornecido se a recepcionista passou algum (ex: '11999998888' ou 'gestor@clinica.com'), ou 'null'"
    )


# ============================================================================
# RECEPTIONIST LM (isolated from main SDR model)
# ============================================================================

_receptionist_lm: Optional[object] = None
_receptionist_lm_initialized: bool = False   # sentinel: tried at least once
_receptionist_lm_lock = threading.Lock()     # prevents double-init under parallel threads


def _resolve_api_key(model: str, settings, api_base: Optional[str] = None) -> Optional[str]:
    """
    Infer the right API key from the model string prefix.
    Order: RECEPTIONIST_API_KEY → provider key → GLM dotenv fallback.

    api_base: the already-resolved base URL (after bigmodel/non-GLM correction).
    Uses this instead of settings.receptionist_api_base to avoid returning the
    GLM key when api_base was cleared because the model is not a GLM model.
    """
    import os

    # 1. Explicit override always wins
    if settings.receptionist_api_key:
        return settings.receptionist_api_key

    model_lower = model.lower()
    resolved_base = api_base or ""

    # 2. GLM models — includes hyphen-key dotenv fallback
    if "glm" in model_lower or "bigmodel" in resolved_base:
        key = settings.glm_api_key or os.environ.get("GLM_API_KEY")
        if not key:
            try:
                from dotenv import dotenv_values
                from pathlib import Path
                env_vals = dotenv_values(Path(".env"))
                key = env_vals.get("GLM-API-KEY") or env_vals.get("GLM_API_KEY")
            except ImportError:
                pass
        return key

    # 3. Standard providers
    if model_lower.startswith("openai/"):
        return settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if model_lower.startswith("anthropic/"):
        return settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if model_lower.startswith("groq/"):
        return settings.groq_api_key or os.environ.get("GROQ_API_KEY")

    return None


def _get_receptionist_lm():
    """
    Returns a DSPy LM for the receptionist simulator.
    Configured via RECEPTIONIST_MODEL / RECEPTIONIST_API_BASE / RECEPTIONIST_API_KEY.
    Falls back to the currently configured DSPy LM if key is unavailable.
    Initializes only once — result is cached.
    """
    global _receptionist_lm, _receptionist_lm_initialized
    if _receptionist_lm_initialized:          # fast path (no lock)
        return _receptionist_lm
    with _receptionist_lm_lock:
        if _receptionist_lm_initialized:      # double-check inside lock
            return _receptionist_lm
        _receptionist_lm_initialized = True   # mark as tried regardless of outcome

    try:
        from app.core.config import get_settings
        settings = get_settings()

        model    = settings.receptionist_model
        api_base = settings.receptionist_api_base or None

        # Normalize: if no provider prefix (no "/"), infer from api_base.
        # GLM / other OpenAI-compatible endpoints → prefix with "openai/"
        if "/" not in model:
            model = f"openai/{model}"

        # If api_base points to GLM but the model is not GLM, drop it —
        # otherwise gpt-4o-mini (and other non-GLM models) get routed to Zhipu
        if api_base and "bigmodel" in api_base and "glm" not in model.lower():
            api_base = None

        # Pass resolved api_base so key resolution uses the post-correction value
        api_key  = _resolve_api_key(model, settings, api_base=api_base)

        if not api_key:
            print(f"  ⚠️  API key não encontrada para {model} — recepcionista usará o LM padrão do DSPy")
            return None

        kwargs = dict(
            model=model,
            api_key=api_key,
            temperature=0.7,   # higher temp = more varied receptionist behavior
            max_tokens=settings.glm_max_tokens,
            timeout=settings.glm_timeout,
        )
        if api_base:
            kwargs["api_base"] = api_base

        _receptionist_lm = dspy.LM(**kwargs)
        print(f"  ✅ Recepcionista usando {model} (max_tokens={settings.glm_max_tokens}, timeout={settings.glm_timeout}s)")
        return _receptionist_lm

    except Exception as e:
        print(f"  ⚠️  Erro ao inicializar LM da recepcionista: {e} — usando LM padrão")
        return None


# ============================================================================
# RECEPTIONIST SIMULATOR MODULE
# ============================================================================

class ReceptionistSimulator(dspy.Module):
    """
    DSPy module simulating a clinic receptionist.

    Uses GLM-4-Flash as the LLM (isolated from the main SDR model).
    Supports 5 profiles × 5 policies = 25 behavioral combinations.
    Profile escalates automatically based on turns_without_progress.
    """

    def __init__(self):
        super().__init__()
        self.respond = dspy.ChainOfThought(ReceptionistSignature)

    def forward(
        self,
        gatekeeper_profile: str,
        clinic_policy: str,
        clinic_name: str,
        conversation_history: list,
        latest_agent_message: str,
        turn_number: int,
        turns_without_progress: int = 0,
    ) -> dict:
        """
        Generate the receptionist's response to Sofia's latest message.

        Args:
            gatekeeper_profile:     blocker | curious | helpful | busy | protocol
            clinic_policy:          FILTER_FIRST | NO_DIRECT_CONTACT | EMAIL_GATE |
                                    OPEN_TO_PARTNERS | STRICT_TRIAGE
            clinic_name:            clinic being contacted
            conversation_history:   full history [{role, content}]
            latest_agent_message:   Sofia's last message
            turn_number:            current turn (starts at 1)
            turns_without_progress: consecutive turns with no contact/progress

        Returns:
            {
                "reasoning":           str,
                "response":            str,
                "current_profile":     str,
                "intent_detected":     str,
                "confidence":          float,
                "conversation_ended":  bool,
                "contact_provided":    str | None,
            }
        """
        # Apply escalation before calling the LM (so the LM sees the updated profile)
        effective_profile = _apply_escalation(gatekeeper_profile, turns_without_progress)

        lm = _get_receptionist_lm()

        if lm:
            with dspy.context(lm=lm):
                result = self.respond(
                    gatekeeper_profile=effective_profile,
                    clinic_policy=clinic_policy,
                    clinic_name=clinic_name,
                    conversation_history=str(conversation_history),
                    latest_agent_message=latest_agent_message,
                    turn_number=str(turn_number),
                    turns_without_progress=str(turns_without_progress),
                )
        else:
            result = self.respond(
                gatekeeper_profile=effective_profile,
                clinic_policy=clinic_policy,
                clinic_name=clinic_name,
                conversation_history=str(conversation_history),
                latest_agent_message=latest_agent_message,
                turn_number=str(turn_number),
                turns_without_progress=str(turns_without_progress),
            )

        response = (result.response or "").strip()

        ended_raw = (result.conversation_ended or "false").lower().strip()
        conversation_ended = ended_raw == "true"

        contact_raw = (result.contact_provided or "null").strip()
        contact = None if contact_raw.lower() == "null" else contact_raw

        try:
            confidence = float(result.confidence)
        except (ValueError, TypeError):
            confidence = 0.5

        current_profile = (result.current_profile or effective_profile).strip().lower()

        return {
            "reasoning":          result.reasoning or "",
            "response":           response,
            "current_profile":    current_profile,
            "intent_detected":    (result.intent_detected or "unclear").strip().lower(),
            "confidence":         round(confidence, 2),
            "conversation_ended": conversation_ended,
            "contact_provided":   contact,
        }


# ============================================================================
# PROFILE ESCALATION
# ============================================================================

def _apply_escalation(profile: str, turns_without_progress: int) -> str:
    """
    Returns the effective profile after applying escalation rules.
    The escalated profile is passed to the LM so it behaves accordingly.
    """
    rule = PROFILE_ESCALATION.get(profile)
    if rule is None:
        return profile  # blocker and protocol don't escalate
    threshold, escalated = rule
    if turns_without_progress >= threshold:
        return escalated
    return profile


# ============================================================================
# BACKWARD COMPAT — ReceptionistScenario enum + singleton
# ============================================================================

from enum import Enum


class ReceptionistScenario(str, Enum):
    """
    Legacy 6-scenario enum. Maps to profile/policy combinations.
    Kept for backward compatibility with existing callers.
    """
    COOPERATIVE        = "cooperative"
    ASK_DATA_THEN_PASS = "ask_data_then_pass"
    REVERSE_CONTACT    = "reverse_contact"
    EMAIL_ONLY         = "email_only"
    SOFT_REFUSAL       = "soft_refusal"
    HARD_REFUSAL       = "hard_refusal"


# Expected outcomes per scenario (legacy)
SCENARIO_EXPECTED_OUTCOMES = {
    ReceptionistScenario.COOPERATIVE:        "decisor_captured",
    ReceptionistScenario.ASK_DATA_THEN_PASS: "decisor_captured",
    ReceptionistScenario.REVERSE_CONTACT:    "denied",
    ReceptionistScenario.EMAIL_ONLY:         "decisor_captured",
    ReceptionistScenario.SOFT_REFUSAL:       "decisor_captured",
    ReceptionistScenario.HARD_REFUSAL:       "denied",
}


def scenario_to_persona(scenario: ReceptionistScenario) -> tuple:
    """Convert legacy scenario to (gatekeeper_profile, clinic_policy)."""
    return SCENARIO_TO_PERSONA[scenario.value]


_receptionist_sim_singleton: Optional[ReceptionistSimulator] = None


def get_receptionist_sim() -> ReceptionistSimulator:
    """Returns a singleton ReceptionistSimulator."""
    global _receptionist_sim_singleton
    if _receptionist_sim_singleton is None:
        _receptionist_sim_singleton = ReceptionistSimulator()
    return _receptionist_sim_singleton
