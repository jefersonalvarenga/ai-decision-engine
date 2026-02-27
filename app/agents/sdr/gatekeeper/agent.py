"""
Gatekeeper Agent - DSPy module for collecting manager contact from reception
"""

import dspy
import re
from typing import Optional
from .signature import GatekeeperSignature
from .utils import safe_str


MAX_ATTEMPTS = 5          # Force failed after N total agent messages without progress
MAX_OBJECTION_TURNS = 3   # Force failed after N handling_objection responses
                           # 3 permite: 1) assunto comercial 2) pitch EasyScale 3) pivot email


# Phrases indicating the reception went to fetch the manager — agent should WAIT, not reply
WAIT_PATTERNS = [
    "só um instante",
    "um momento",
    "um minutinho",
    "um segundo",
    "aguarda",
    "aguarde",
    "deixa eu ver",
    "vou chamar",
    "vou verificar",
    "vou perguntar",
    "vou avisar",
    "vou falar com ele",
    "vou falar com ela",
    "já vou chamar",
    "já chamo",
    "hold on",
    "one moment",
]

# Phrases that signal immediate/definitive rejection — skip straight to failed
IMMEDIATE_REJECTION_PATTERNS = [
    "já disse que não",
    "pare de insistir",
    "não entre em contato",
    "não quero ser contactado",
    "não quero ser contatado",
    "não fornecemos contato",
    "não vou passar nenhum",
    "bloqueado",
    "vou bloquear",
]


class GatekeeperAgent(dspy.Module):
    """
    Agent that talks to clinic reception to get the manager's contact.
    Uses Chain of Thought for better reasoning about conversation flow.

    Exit rules:
    - success: phone (8+ digits) or email (@) received → send thanks, stop
    - failed:  max 2 handling_objection turns OR immediate rejection → send goodbye, stop
    """

    def __init__(self, max_attempts: int = MAX_ATTEMPTS):
        super().__init__()
        self.process = dspy.ChainOfThought(GatekeeperSignature)
        self.max_attempts = max_attempts

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        """Extract only digits from phone number"""
        if not phone or phone.lower() == "null":
            return None
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 10:
            return digits
        return None

    def _clean_email(self, email: Optional[str]) -> Optional[str]:
        """Extract and validate email address"""
        if not email or email.lower() == "null":
            return None
        cleaned = email.strip()
        # Basic email validation: must contain @ and a dot after @
        if re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
            return cleaned.lower()
        return None

    def _clean_name(self, name: Optional[str]) -> Optional[str]:
        """Clean extracted name"""
        if not name or name.lower() == "null":
            return None
        cleaned = " ".join(name.strip().split())
        return cleaned if cleaned else None

    def _is_wait_signal(self, message: Optional[str]) -> bool:
        """
        Detect if the reception is signaling to wait (went to fetch manager).
        In this case the agent should NOT reply — just hold.
        """
        if not message:
            return False
        msg_lower = message.lower()
        return any(pattern in msg_lower for pattern in WAIT_PATTERNS)

    def _is_immediate_rejection(self, message: Optional[str]) -> bool:
        """
        Detect hard/definitive rejection that warrants immediate graceful exit.
        """
        if not message:
            return False
        msg_lower = message.lower()
        return any(pattern in msg_lower for pattern in IMMEDIATE_REJECTION_PATTERNS)

    def _count_objection_turns(self, conversation_history: list) -> int:
        """
        Conta turnos reais de handling_objection no histórico.
        Usa o campo 'stage' por turno quando disponível (fonte exata).
        Fallback: heurística de contagem se stage não estiver no histórico.
        """
        agent_turns = [t for t in conversation_history if t.get("role") == "agent"]

        # Contagem exata: usa stage salvo por turno (quando n8n passa stage no histórico)
        turns_with_stage = [t for t in agent_turns if t.get("stage")]
        if turns_with_stage:
            return sum(1 for t in turns_with_stage if t.get("stage") == "handling_objection")

        # Fallback heurístico: assume que os 2 primeiros turnos são opening/requesting
        return max(0, len(agent_turns) - 2)

    def forward(
        self,
        clinic_name: str,
        conversation_history: list,
        latest_message: Optional[str],
        current_hour: int,
        attempt_count: int,
    ) -> dict:
        """
        Process the conversation and generate next response.

        Returns:
            dict with response_message, conversation_stage, extracted info, etc.
        """
        # --- SMART FALLBACK 0: Wait signal — acknowledge briefly and hold ---
        if self._is_wait_signal(latest_message):
            return {
                "reasoning": (
                    f"Reception signaled to wait: '{latest_message}'. "
                    "Sending short acknowledgment and holding for next message."
                ),
                "response_message": "Certo!",
                "conversation_stage": "requesting",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
                "should_send_message": True,
            }

        # --- SMART FALLBACK 1: Immediate rejection — graceful exit ---
        if self._is_immediate_rejection(latest_message):
            return {
                "reasoning": (
                    f"Immediate rejection detected: '{latest_message}'. "
                    "Sending graceful goodbye."
                ),
                "response_message": "Entendido, desculpe o incômodo. Bom trabalho a todos!",
                "conversation_stage": "failed",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
                "should_send_message": True,
            }

        result = self.process(
            clinic_name=clinic_name,
            conversation_history=str(conversation_history) if conversation_history else "[]",
            latest_message=latest_message or "PRIMEIRA_MENSAGEM",
            current_hour=str(current_hour),
            attempt_count=str(attempt_count),
        )

        # Parse and clean outputs
        extracted_contact = self._clean_phone(safe_str(result.extracted_contact, "null"))
        extracted_email = self._clean_email(safe_str(result.extracted_email, "null"))
        extracted_name = self._clean_name(safe_str(result.extracted_name, "null"))

        # Determine if should continue
        should_continue = safe_str(result.should_continue, "true").lower().strip() == "true"

        # Validate stage
        valid_stages = ["opening", "requesting", "handling_objection", "success", "failed"]
        stage = safe_str(result.conversation_stage, "handling_objection").lower().strip()
        if stage not in valid_stages:
            stage = "handling_objection"

        # --- PÓS-CHECK: LLM confirmou que é objeção → conta objeções reais e decide ---
        if stage == "handling_objection":
            prior_objections = self._count_objection_turns(conversation_history)
            total_objections = prior_objections + 1  # +1 pela atual
            if total_objections >= MAX_OBJECTION_TURNS:
                stage = "failed"
                response_message = safe_str(result.response_message, "").strip()
                if not response_message or response_message.lower() == "null":
                    response_message = "Compreendo, obrigado pela atenção! Sucesso à clínica."

        # Get response message
        response_message = safe_str(result.response_message, "").strip()

        # --- SMART FALLBACKS ---

        # 1. Phone contact received → success
        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        # 2. Email contact received → success
        if extracted_email and not extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        # 3. Force failed if max total attempts reached
        if attempt_count >= self.max_attempts and stage in ["opening", "requesting", "handling_objection"]:
            stage = "failed"
            response_message = response_message or "Obrigado pelo tempo! Bom trabalho."
            should_continue = True  # Send the goodbye message

        # 4. Success → stop (no more messages needed beyond the thank-you)
        if stage == "success":
            should_continue = False

        # 5. Failed → send goodbye if we have one, then stop
        if stage == "failed":
            if not response_message or response_message.lower() == "null":
                response_message = "Entendido, obrigado pela atenção!"
            should_continue = True  # Send the goodbye message

        # 6. Empty response → don't send
        if not response_message or response_message.lower() == "null":
            should_continue = False
            response_message = ""

        return {
            "reasoning": safe_str(result.reasoning, ""),
            "response_message": response_message,
            "conversation_stage": stage,
            "extracted_manager_contact": extracted_contact,
            "extracted_manager_email": extracted_email,
            "extracted_manager_name": extracted_name,
            "should_send_message": should_continue,
        }
