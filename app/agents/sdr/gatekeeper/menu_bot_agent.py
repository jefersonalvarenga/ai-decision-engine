"""
Menu Bot Agent - Bypass de bots de menu enviando 'falar com atendente'.

Fluxo:
  1. Tentativas 1 e 2: envia 'falar com atendente' (fixo, sem LLM)
  2. Após MAX_BYPASS_ATTEMPTS: encerra com failed
"""

MAX_BYPASS_ATTEMPTS = 2


class MenuBotAgent:
    def __init__(self):
        pass

    def forward(
        self,
        clinic_name: str,
        conversation_history: list,
        latest_message: str,
        attempt_count: int,
    ) -> dict:
        # Esgotado — encerra sem chamar LLM
        if attempt_count >= MAX_BYPASS_ATTEMPTS:
            return {
                "response_message": "Entendido, obrigado pela atenção!",
                "conversation_stage": "menu_blocked",
                "should_send_message": True,
                "reasoning": "Bypass esgotado — bot não tem saída para humano.",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
            }

        return {
            "response_message": "falar com atendente",
            "conversation_stage": "handling_menu_bot",
            "should_send_message": True,
            "reasoning": f"Tentativa {attempt_count + 1} de bypass: envia 'falar com atendente'.",
            "extracted_manager_contact": None,
            "extracted_manager_email": None,
            "extracted_manager_name": None,
        }
