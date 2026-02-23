"""
Gatekeeper Agent - DSPy module for collecting manager contact from reception
"""

import dspy
import re
from typing import Optional
from .signature import GatekeeperSignature
from .utils import safe_str


MAX_ATTEMPTS = 5  # Force failed after N attempts without progress


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


class GatekeeperAgent(dspy.Module):
    """
    Agent that talks to clinic reception to get the manager's contact.
    Uses Chain of Thought for better reasoning about conversation flow.
    """

    def __init__(self, max_attempts: int = MAX_ATTEMPTS):
        super().__init__()
        self.process = dspy.ChainOfThought(GatekeeperSignature)
        self.max_attempts = max_attempts

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        """Extract only digits from phone number"""
        if not phone or phone.lower() == "null":
            return None
        # Remove everything except digits
        digits = re.sub(r"\D", "", phone)
        # Brazilian phone numbers have 10-11 digits (with area code)
        if len(digits) >= 10:
            return digits
        return None

    def _clean_name(self, name: Optional[str]) -> Optional[str]:
        """Clean extracted name"""
        if not name or name.lower() == "null":
            return None
        # Remove extra whitespace
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

        Args:
            clinic_name: Name of the clinic
            conversation_history: List of {role, content} turns
            latest_message: Last message from reception (None if first message)
            current_hour: Current hour (0-23) for greeting
            attempt_count: Number of messages sent by agent

        Returns:
            dict with response_message, conversation_stage, extracted info, etc.
        """
        # --- SMART FALLBACK 0: Wait signal — acknowledge briefly and hold ---
        # Reception said "só um instante" / "um momento" / "vou chamar" etc.
        # Reply with a short "Certo!" to confirm we're alive, then wait.
        if self._is_wait_signal(latest_message):
            return {
                "reasoning": (
                    f"Reception signaled to wait: '{latest_message}'. "
                    "Sending short acknowledgment and holding for next message."
                ),
                "response_message": "Certo!",
                "conversation_stage": "requesting",
                "extracted_manager_contact": None,
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
        extracted_name = self._clean_name(safe_str(result.extracted_name, "null"))

        # Determine if should continue
        should_continue = safe_str(result.should_continue, "true").lower().strip() == "true"

        # Validate stage
        valid_stages = ["opening", "requesting", "handling_objection", "success", "failed"]
        stage = safe_str(result.conversation_stage, "handling_objection").lower().strip()
        if stage not in valid_stages:
            stage = "handling_objection"  # Safe default

        # Get response message
        response_message = safe_str(result.response_message, "").strip()

        # --- SMART FALLBACKS ---

        # 1. If we got a contact, stage must be success
        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        # 2. Force failed if max attempts reached without progress
        if attempt_count >= self.max_attempts and stage in ["opening", "requesting", "handling_objection"]:
            stage = "failed"
            should_continue = False

        # 3. Terminal stages always stop
        if stage in ["success", "failed"]:
            should_continue = False

        # 4. If response_message is "null", empty or whitespace — don't send
        if not response_message or response_message.lower() == "null":
            should_continue = False
            response_message = ""

        return {
            "reasoning": safe_str(result.reasoning, ""),
            "response_message": response_message,
            "conversation_stage": stage,
            "extracted_manager_contact": extracted_contact,
            "extracted_manager_name": extracted_name,
            "should_send_message": should_continue,
        }
