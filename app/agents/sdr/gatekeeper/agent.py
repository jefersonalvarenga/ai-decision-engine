"""
Gatekeeper Agent - DSPy module for collecting manager contact from reception
"""

import dspy
import re
from typing import Optional
from .signature import GatekeeperSignature


class GatekeeperAgent(dspy.Module):
    """
    Agent that talks to clinic reception to get the manager's contact.
    Uses Chain of Thought for better reasoning about conversation flow.
    """

    def __init__(self):
        super().__init__()
        self.process = dspy.ChainOfThought(GatekeeperSignature)

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
        result = self.process(
            clinic_name=clinic_name,
            conversation_history=str(conversation_history) if conversation_history else "[]",
            latest_message=latest_message or "PRIMEIRA_MENSAGEM",
            current_hour=str(current_hour),
            attempt_count=str(attempt_count),
        )

        # Parse and clean outputs
        extracted_contact = self._clean_phone(result.extracted_contact)
        extracted_name = self._clean_name(result.extracted_name)

        # Determine if should continue
        should_continue = result.should_continue.lower().strip() == "true"

        # Validate stage
        valid_stages = ["opening", "requesting", "handling_objection", "success", "failed"]
        stage = result.conversation_stage.lower().strip()
        if stage not in valid_stages:
            stage = "handling_objection"  # Safe default

        # If we got a contact, stage should be success
        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        return {
            "reasoning": result.reasoning,
            "response_message": result.response_message.strip(),
            "conversation_stage": stage,
            "extracted_manager_contact": extracted_contact,
            "extracted_manager_name": extracted_name,
            "should_send_message": should_continue,
        }
