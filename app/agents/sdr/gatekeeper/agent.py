"""
Gatekeeper Agent - DSPy module for collecting manager contact from reception
"""

import dspy
import re
from pathlib import Path
from typing import Optional
from .signature import GatekeeperSignature
from .utils import safe_str


class GatekeeperAgent(dspy.Module):
    """
    Agent that talks to clinic reception to get the manager's contact.
    Uses Chain of Thought for better reasoning about conversation flow.
    All decisions (wait, reject, continue, stage) are made by the LLM.

    Otimização:
    - Se artifacts/gatekeeper_optimized.json existir, carrega os few-shot demos automaticamente.
    - Gere o artifact com: python -m app.agents.sdr.optimize_gatekeeper
    - load_optimized=False força uso do modelo base (usado pelo próprio optimizer).
    """

    _ARTIFACT_PATH = Path(__file__).parent.parent.parent.parent.parent / "artifacts" / "gatekeeper_optimized.json"

    def __init__(self, load_optimized: bool = True):
        super().__init__()
        self.process = dspy.ChainOfThought(GatekeeperSignature)

        if load_optimized and self._ARTIFACT_PATH.exists():
            try:
                self.load(str(self._ARTIFACT_PATH))
                size_kb = self._ARTIFACT_PATH.stat().st_size // 1024
                print(f"✅ GatekeeperAgent: demos otimizados carregados ({size_kb}KB)")
            except Exception as e:
                print(f"⚠️  GatekeeperAgent: falha ao carregar {self._ARTIFACT_PATH.name} — {e}")

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        if not phone or phone.lower() == "null":
            return None
        digits = re.sub(r"\D", "", phone)
        return digits if len(digits) >= 10 else None

    def _clean_email(self, email: Optional[str]) -> Optional[str]:
        if not email or email.lower() == "null":
            return None
        cleaned = email.strip()
        if re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
            return cleaned.lower()
        return None

    def _clean_name(self, name: Optional[str]) -> Optional[str]:
        if not name or name.lower() == "null":
            return None
        cleaned = " ".join(name.strip().split())
        return cleaned if cleaned else None

    def forward(
        self,
        clinic_name: str,
        sdr_name: str = "Vera",
        conversation_history: list = None,
        latest_message: Optional[str] = None,
        current_hour: int = 12,
        current_weekday: int = 0,
        detected_persona: str = "unknown",
    ) -> dict:
        result = self.process(
            clinic_name=clinic_name,
            sdr_name=sdr_name,
            conversation_history=str(conversation_history) if conversation_history else "[]",
            latest_message=latest_message or "PRIMEIRA_MENSAGEM",
            current_hour=str(current_hour),
            current_weekday=str(current_weekday),
            detected_persona=detected_persona,
        )

        extracted_contact = self._clean_phone(safe_str(result.extracted_contact, "null"))
        extracted_email = self._clean_email(safe_str(result.extracted_email, "null"))
        extracted_name = self._clean_name(safe_str(result.extracted_name, "null"))
        should_continue = safe_str(result.should_continue, "true").lower().strip() == "true"

        valid_stages = ["opening", "requesting", "handling_objection", "success", "failed"]
        stage = safe_str(result.conversation_stage, "").lower().strip()
        if stage not in valid_stages:
            print(f"⚠️  GatekeeperAgent: stage inválido recebido do LLM: '{stage}' — mantendo como está")

        response_message = safe_str(result.response_message, "").strip()

        # Promoção de stage para success quando contato foi extraído (validação de formato)
        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"
        if extracted_email and not extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

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
