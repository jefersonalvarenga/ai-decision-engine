"""
Closer Agent - DSPy module for scheduling meetings with clinic managers
"""

import dspy
import re
from typing import Optional, List
from datetime import datetime
from .signature import CloserSignature


class CloserAgent(dspy.Module):
    """
    Agent that talks to clinic managers to schedule demo meetings.
    Uses Chain of Thought for better reasoning about objections and timing.
    """

    def __init__(self):
        super().__init__()
        self.process = dspy.ChainOfThought(CloserSignature)

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[str]:
        """
        Parse and validate datetime string to ISO format.
        Returns None if invalid or 'null'.
        """
        if not dt_str or dt_str.lower().strip() == "null":
            return None

        # Try to parse various formats
        formats_to_try = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]

        cleaned = dt_str.strip()

        for fmt in formats_to_try:
            try:
                parsed = datetime.strptime(cleaned, fmt)
                return parsed.isoformat()
            except ValueError:
                continue

        # Try to extract datetime pattern from string
        pattern = r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})"
        match = re.search(pattern, cleaned)
        if match:
            try:
                date_str = f"{match.group(1)} {match.group(2)}"
                parsed = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                return parsed.isoformat()
            except ValueError:
                pass

        return None

    def _split_messages(self, message: str) -> List[str]:
        """Split multiple messages separated by |||"""
        if "|||" in message:
            return [m.strip() for m in message.split("|||") if m.strip()]
        return [message.strip()]

    def forward(
        self,
        manager_name: str,
        clinic_name: str,
        clinic_specialty: Optional[str],
        conversation_history: list,
        latest_message: Optional[str],
        available_slots: List[str],
        current_hour: int,
        attempt_count: int,
    ) -> dict:
        """
        Process the conversation and generate next response.

        Args:
            manager_name: Name of the manager (e.g., "Dr. Marcos")
            clinic_name: Name of the clinic
            clinic_specialty: Specialty (odonto, estética, etc.)
            conversation_history: List of {role, content} turns
            latest_message: Last message from manager (None if first message)
            available_slots: List of available time slots
            current_hour: Current hour (0-23) for greeting
            attempt_count: Number of messages sent by agent

        Returns:
            dict with response_message, conversation_stage, meeting_datetime, etc.
        """
        # Format available slots as comma-separated string
        slots_str = ", ".join(available_slots) if available_slots else "Sem horários disponíveis"

        result = self.process(
            manager_name=manager_name,
            clinic_name=clinic_name,
            clinic_specialty=clinic_specialty or "saúde",
            conversation_history=str(conversation_history) if conversation_history else "[]",
            latest_message=latest_message or "PRIMEIRA_MENSAGEM",
            available_slots=slots_str,
            current_hour=str(current_hour),
            attempt_count=str(attempt_count),
        )

        # Safe attribute access — GLM-5 sometimes returns malformed types
        def safe_str(val, default="") -> str:
            if val is None:
                return default
            if isinstance(val, str):
                return val
            return str(val)

        # Parse datetime if meeting was scheduled
        meeting_datetime = self._parse_datetime(safe_str(result.meeting_datetime, "null"))

        # Determine if should continue
        should_continue = safe_str(result.should_continue, "true").lower().strip() == "true"

        # Validate stage
        valid_stages = ["greeting", "pitching", "proposing_time", "confirming", "scheduled", "lost"]
        stage = safe_str(result.conversation_stage, "pitching").lower().strip()
        if stage not in valid_stages:
            stage = "pitching"  # Safe default

        # --- SMART FALLBACKS (mirroring gatekeeper patterns) ---

        # 1. If datetime extracted but LLM didn't classify as scheduled/confirming,
        #    clear the datetime (LLM likely hallucinated it during pitch/propose)
        if meeting_datetime and stage not in ["scheduled", "confirming"]:
            meeting_datetime = None

        # 1b. If scheduled but latest_message is a question (contains "?"),
        #     it's likely a counter-proposal, not a confirmation → downgrade to confirming
        if stage == "scheduled" and latest_message and "?" in latest_message:
            stage = "confirming"
            meeting_datetime = None

        # 2. If scheduled but no datetime, downgrade to confirming
        if stage == "scheduled" and not meeting_datetime:
            stage = "confirming"

        # 3. Can't propose time without available slots
        if stage == "proposing_time" and not available_slots:
            stage = "pitching"

        # 4. Force lost if 5+ attempts without progress
        if attempt_count >= 5 and stage in ["greeting", "pitching"]:
            stage = "lost"
            should_continue = False

        # 5. Terminal stages always stop
        if stage in ["scheduled", "lost"]:
            should_continue = False

        # Get response message (may contain multiple messages)
        response_message = safe_str(result.response_message, "Podemos continuar?").strip()

        return {
            "reasoning": safe_str(result.reasoning, ""),
            "response_message": response_message,
            "conversation_stage": stage,
            "meeting_datetime": meeting_datetime,
            "meeting_confirmed": meeting_datetime is not None,
            "should_send_message": should_continue,
        }
