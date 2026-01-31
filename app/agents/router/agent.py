"""
Router Agent - DSPy module for intent classification

Classifies patient messages into intentions that determine which
specialized agents should handle the conversation.
"""

import dspy
import re
from typing import List, Dict, Any
from .signatures import RouterSignature, IntentType


class RouterAgent(dspy.Module):
    """
    Agent that classifies patient messages into intentions.
    Uses Chain of Thought for better reasoning about context.
    """

    def __init__(self):
        super().__init__()
        self.process = dspy.ChainOfThought(RouterSignature)

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history as string for LLM"""
        if not history:
            return "Sem histórico anterior."

        formatted = []
        for turn in history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            prefix = "Paciente" if role == "human" else "Agente"
            formatted.append(f"{prefix}: {content}")

        return "\n".join(formatted)

    def _parse_intentions(self, intentions_raw: Any) -> List[str]:
        """Parse and validate intentions from LLM output"""
        valid_intents = {item.value for item in IntentType}

        # Handle different output formats
        if isinstance(intentions_raw, list):
            intentions_list = intentions_raw
        elif isinstance(intentions_raw, str):
            # Try to parse as list string: "['A', 'B']" or "A, B"
            cleaned = intentions_raw.strip()
            if cleaned.startswith("["):
                try:
                    import ast
                    intentions_list = ast.literal_eval(cleaned)
                except (ValueError, SyntaxError):
                    intentions_list = [i.strip().strip("'\"") for i in cleaned[1:-1].split(",")]
            else:
                intentions_list = [i.strip() for i in cleaned.split(",")]
        else:
            intentions_list = []

        # Filter only valid intentions
        cleaned_intentions = [
            intent.strip().upper()
            for intent in intentions_list
            if intent.strip().upper() in valid_intents
        ]

        # Fallback to UNCLASSIFIED if empty
        if not cleaned_intentions:
            cleaned_intentions = [IntentType.UNCLASSIFIED.value]

        return cleaned_intentions

    def _parse_confidence(self, confidence_raw: Any) -> float:
        """Parse confidence value from LLM output"""
        try:
            if isinstance(confidence_raw, (int, float)):
                return float(confidence_raw)
            if isinstance(confidence_raw, str):
                # Extract number from string
                match = re.search(r"[\d.]+", confidence_raw)
                if match:
                    return float(match.group())
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    def forward(
        self,
        latest_incoming: str,
        history: List[Dict[str, str]],
        intake_status: str,
        schedule_status: str,
        reschedule_status: str,
        cancel_status: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Classify the patient message and return intentions.

        Args:
            latest_incoming: Latest message from patient
            history: Conversation history as list of {role, content}
            intake_status: Current intake status
            schedule_status: Current scheduling status
            reschedule_status: Current rescheduling status
            cancel_status: Current cancellation status
            language: Patient's language

        Returns:
            dict with intentions, reasoning, confidence
        """
        # Format history for LLM
        history_str = self._format_history(history)

        # Call DSPy module
        result = self.process(
            latest_incoming=latest_incoming,
            history=history_str,
            intake_status=intake_status,
            schedule_status=schedule_status,
            reschedule_status=reschedule_status,
            cancel_status=cancel_status,
            language=language,
        )

        # Parse outputs
        intentions = self._parse_intentions(result.intentions)
        confidence = self._parse_confidence(result.confidence)

        return {
            "intentions": intentions,
            "reasoning": str(result.reasoning).strip(),
            "confidence": confidence,
        }
