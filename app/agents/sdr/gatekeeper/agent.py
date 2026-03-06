"""
Gatekeeper Agent - DSPy module for collecting manager contact from reception
"""

import dspy
import re
from pathlib import Path
from typing import Optional
from .signature import GatekeeperSignature
from .utils import safe_str


MAX_OBJECTION_TURNS = 3   # Max handling_objection responses before failing.
                           # 3 permite: 1) assunto comercial 2) pitch EasyScale 3) pivot email
                           # Fail triggers on the (N+1)-th objection, so the pivot email IS sent
                           # and the conversation stays open for the human to reply with an email.


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
    - success:  phone (8+ digits) or email (@) received → send thanks, stop
    - failed:   MAX_OBJECTION_TURNS handling_objection turns OR immediate rejection → send goodbye, stop
    Note: total message count (attempt_count) is passed to the LLM as context only — it
    does NOT trigger forced termination. Only objection turns count towards the limit.

    Otimização:
    - Se artifacts/gatekeeper_optimized.json existir, carrega os few-shot demos automaticamente.
    - Gere o artifact com: python -m app.agents.sdr.optimize_gatekeeper
    - load_optimized=False força uso do modelo base (usado pelo próprio optimizer).
    """

    # agent.py está em: app/agents/sdr/gatekeeper/agent.py
    # 5x .parent chega na raiz do projeto (ai-decision-engine/)
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

        # Fallback conservativo: sem stage no histórico, não inflar a contagem.
        # Deixa o LLM decidir quando desistir conforme a signature.
        # O risco de inflação é alto em conversas eternas (muitos turnos acumulados).
        return 0

    def forward(
        self,
        clinic_name: str,
        sdr_name: str = "Vera",
        conversation_history: list = None,
        latest_message: Optional[str] = None,
        current_hour: int = 12,
        current_weekday: int = 0,
        attempt_count: int = 0,
    ) -> dict:
        """
        Process the conversation and generate next response.

        Returns:
            dict with response_message, conversation_stage, extracted info, etc.
        """
        # Track before conversion so we can force-send the first message later
        is_first_message = (latest_message is None)

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
                "response_message": "Entendido! Se um dia quiser — a gente desafoga 60% do repetitivo. Me chama.",
                "conversation_stage": "failed",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
                "should_send_message": True,
            }

        result = self.process(
            clinic_name=clinic_name,
            sdr_name=sdr_name,
            conversation_history=str(conversation_history) if conversation_history else "[]",
            latest_message=latest_message or "PRIMEIRA_MENSAGEM",
            current_hour=str(current_hour),
            current_weekday=str(current_weekday),
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

        # Get response message
        response_message = safe_str(result.response_message, "").strip()

        # --- HARD OVERRIDE: primeira mensagem deve sempre ser enviada ---
        # O LLM pode confundir "recepção não respondeu" com sinal de espera e
        # retornar should_continue=false. Quando é a primeira mensagem, forçamos envio.
        if is_first_message:
            should_continue = True
            if not response_message or response_message.lower() == "null":
                # Fallback: abre com confirmação da clínica (estratégia comprovada)
                greeting = "Bom dia" if current_hour < 12 else "Boa tarde" if current_hour < 18 else "Boa noite"
                response_message = f"{greeting}, é da {clinic_name}?"

        # --- SMART FALLBACKS ---

        # 1. Phone contact received → success (checked BEFORE objection count, so a contact
        #    given on the 3rd objection turn still wins over the objection limit)
        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        # 2. Email contact received → success (same priority logic as phone)
        if extracted_email and not extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        # --- PÓS-CHECK: LLM confirmou que é objeção → conta objeções reais e decide ---
        # Runs AFTER contact check so a contact given on the Nth objection turn is not lost.
        if stage == "handling_objection":
            prior_objections = self._count_objection_turns(conversation_history)
            total_objections = prior_objections + 1  # +1 pela atual
            if total_objections > MAX_OBJECTION_TURNS:
                stage = "failed"
                if not response_message or response_message.lower() == "null":
                    response_message = "Ok! Se quiser — a gente desafoga 60% do atendimento. Você foca nos pacientes."

        # 3. Success → send thank-you, then stop (evaluator breaks loop after success stage)
        if stage == "success":
            if not response_message or response_message.lower() == "null":
                response_message = "Obrigado!"
            should_continue = True

        # 4. Failed → send goodbye if we have one, then stop
        if stage == "failed":
            if not response_message or response_message.lower() == "null":
                response_message = "Entendido, obrigado pela atenção!"
            should_continue = True  # Send the goodbye message

        # 5. Empty response → don't send
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
