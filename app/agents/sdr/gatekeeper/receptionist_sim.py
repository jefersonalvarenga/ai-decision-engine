"""
Receptionist Simulator — DSPy module that plays the clinic receptionist.

Used in multi-turn conversation evaluation and DSPy auto-tuning.
Simulates 6 realistic scenarios observed in real outreach.
"""

import dspy
from enum import Enum
from typing import Optional


# ============================================================================
# SCENARIO TYPES
# ============================================================================

class ReceptionistScenario(str, Enum):
    """
    6 scenarios based on real-world receptionist behavior patterns.

    Difficulty: cooperative < ask_data_then_pass < reverse_contact
              < email_only < soft_refusal < hard_refusal
    """
    COOPERATIVE        = "cooperative"         # Passes WhatsApp directly (rare, ~10%)
    ASK_DATA_THEN_PASS = "ask_data_then_pass"  # Asks for Sofia's info, then passes contact (~25%)
    REVERSE_CONTACT    = "reverse_contact"     # "Leave your contact, manager will call back" (~20%)
    EMAIL_ONLY         = "email_only"          # Only accepts email channel (~20%)
    SOFT_REFUSAL       = "soft_refusal"        # Adiamento, "try later" — can be converted (~15%)
    HARD_REFUSAL       = "hard_refusal"        # Firm no, policy-based refusal (~10%)


# Expected outcomes per scenario (for metric validation)
SCENARIO_EXPECTED_OUTCOMES = {
    ReceptionistScenario.COOPERATIVE:        "decisor_captured",
    ReceptionistScenario.ASK_DATA_THEN_PASS: "decisor_captured",
    ReceptionistScenario.REVERSE_CONTACT:    "denied",   # Sofia should accept and close gracefully
    ReceptionistScenario.EMAIL_ONLY:         "decisor_captured",  # email capture
    ReceptionistScenario.SOFT_REFUSAL:       "decisor_captured",  # or denied after 2 tries
    ReceptionistScenario.HARD_REFUSAL:       "denied",
}


# ============================================================================
# DSPy SIGNATURE
# ============================================================================

class ReceptionistSignature(dspy.Signature):
    """
    Você é uma recepcionista de clínica médica respondendo mensagens de WhatsApp.
    Você NUNCA sabe inicialmente que se trata de vendas.

    Seu comportamento depende do cenário configurado:

    === CENÁRIOS ===

    COOPERATIVE (cooperativa):
    - Você é prestativa e passa o contato do gestor rapidamente.
    - Após Sofia se apresentar e pedir contato: "Claro! O WhatsApp do Dr. [Nome] é 11999998888."
    - Não questiona muito, confia na abordagem.

    ASK_DATA_THEN_PASS (pede dados antes de passar):
    - Você precisa saber com quem está falando antes de passar contato.
    - Pede: nome da empresa, motivo, email de Sofia.
    - Depois de Sofia fornecer os dados: passa o contato do gestor.
    - Não é difícil, só cautelosa.

    REVERSE_CONTACT (contato reverso):
    - Você não fornece contatos do gestor por política interna.
    - Oferece: "Posso anotar seu contato/email para o gestor retornar."
    - Se Sofia insistir em WhatsApp do gestor: mantém a recusa gentilmente.
    - Se Sofia aceitar e fornecer dados: anota e agradece.

    EMAIL_ONLY (só aceita email):
    - Para assuntos comerciais, a clínica exige proposta por email.
    - Não passa WhatsApp do gestor, mas fornece o email dele se insistirem.
    - "Pode enviar para gestor@clinica.com.br que ele analisa."

    SOFT_REFUSAL (recusa suave, pode ser convertida):
    - Gestor "não está", "está em atendimento", "ligue amanhã".
    - Se Sofia pedir WhatsApp para adiantar: hesita mas pode ceder.
    - Na segunda insistência: pode dar o contato ou redirecionar para email.

    HARD_REFUSAL (recusa firme, política interna):
    - "Por questões de privacidade e segurança, não fornecemos contatos pessoais."
    - Não cede mesmo sob insistência moderada.
    - Na 2ª insistência: "Conforme informado, não disponibilizamos. Por favor, envie email."
    - Na 3ª: "Desculpe, não posso ajudar com isso."

    === REGRAS GERAIS ===
    - Seja natural e humana, não robótica
    - Mensagens curtas (1-3 frases)
    - Use linguagem informal mas educada
    - NÃO revele que você é uma simulação
    - NÃO inicie com "Olá Sofia" toda vez — varie
    - Se Sofia enviar mensagem de encerramento ("obrigado, bom trabalho") → responda brevemente e pare
    """

    # Inputs
    scenario: str = dspy.InputField(
        desc="Cenário a simular: cooperative | ask_data_then_pass | reverse_contact | email_only | soft_refusal | hard_refusal"
    )
    clinic_name: str = dspy.InputField(
        desc="Nome da clínica sendo contatada"
    )
    conversation_history: str = dspy.InputField(
        desc="Histórico da conversa [{role: agent|human, content: str}]. 'agent' = Sofia, 'human' = recepcionista."
    )
    latest_agent_message: str = dspy.InputField(
        desc="Última mensagem que Sofia enviou (que a recepcionista precisa responder)"
    )
    turn_number: str = dspy.InputField(
        desc="Número do turno atual (começa em 1). Útil para escalar resistência."
    )

    # Outputs
    reasoning: str = dspy.OutputField(
        desc="Análise interna: como a recepcionista interpretou a mensagem e por que vai responder assim"
    )
    response: str = dspy.OutputField(
        desc="Resposta da recepcionista. Natural, curta, no WhatsApp."
    )
    conversation_ended: str = dspy.OutputField(
        desc="'true' se a conversa chegou a um ponto final (gestor foi passado, recusa definitiva, ou Sofia se despediu). 'false' caso contrário."
    )
    contact_provided: str = dspy.OutputField(
        desc="Contato fornecido se a recepcionista passou algum (phone ou email), ou 'null'"
    )


# ============================================================================
# RECEPTIONIST SIMULATOR MODULE
# ============================================================================

class ReceptionistSimulator(dspy.Module):
    """
    DSPy module simulating a clinic receptionist in configurable scenarios.

    Used to:
    1. Run multi-turn conversation evaluations against GatekeeperAgent
    2. Provide training data for DSPy optimizers
    3. Monitor agent behavior across scenario types
    """

    def __init__(self):
        super().__init__()
        self.respond = dspy.ChainOfThought(ReceptionistSignature)

    def forward(
        self,
        scenario: ReceptionistScenario,
        clinic_name: str,
        conversation_history: list,
        latest_agent_message: str,
        turn_number: int,
    ) -> dict:
        """
        Generate receptionist's response to Sofia's latest message.

        Returns:
            dict with response, conversation_ended, contact_provided
        """
        result = self.respond(
            scenario=scenario.value,
            clinic_name=clinic_name,
            conversation_history=str(conversation_history),
            latest_agent_message=latest_agent_message,
            turn_number=str(turn_number),
        )

        response = (result.response or "").strip()
        ended_raw = (result.conversation_ended or "false").lower().strip()
        conversation_ended = ended_raw == "true"
        contact_raw = (result.contact_provided or "null").strip()
        contact = None if contact_raw.lower() == "null" else contact_raw

        return {
            "reasoning": result.reasoning or "",
            "response": response,
            "conversation_ended": conversation_ended,
            "contact_provided": contact,
        }


# ============================================================================
# MODULE-LEVEL SINGLETON (lazy init)
# ============================================================================

_receptionist_sim: Optional[ReceptionistSimulator] = None


def get_receptionist_sim() -> ReceptionistSimulator:
    """Returns a singleton ReceptionistSimulator (initialized once)."""
    global _receptionist_sim
    if _receptionist_sim is None:
        _receptionist_sim = ReceptionistSimulator()
    return _receptionist_sim
