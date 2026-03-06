"""
Menu Bot Agent - Estratégia para bypassar bots de menu e chegar num humano.

Fluxo:
  1. Tenta responder com opção que leva a humano ("falar com atendente", "0", etc.)
  2. Se após MAX_BYPASS_ATTEMPTS o bot continua respondendo → encerra (failed)
"""

import dspy

MAX_BYPASS_ATTEMPTS = 2


class MenuBotSignature(dspy.Signature):
    """
    Você está conversando com um bot de menu automatizado de uma clínica.
    O bot responde com opções numeradas e não entende pedidos livres.
    Seu objetivo é sair do menu e chegar em um atendente humano.

    === ESTRATÉGIA ===

    Tentativa 1 (attempt_count = 0 ou 1):
      Responda com a opção que parece levar a um atendente humano.
      Procure por opções como: "falar com atendente", "outros assuntos",
      "falar com humano", "atendimento", "suporte", "0", "9", etc.
      Se não houver opção óbvia, responda com "0" ou "falar com atendente".
      Use exatamente o texto ou número da opção — sem explicações extras.
      Exemplos: "falar com atendente" / "0" / "3" / "outros"

    Tentativa 2+ (attempt_count >= MAX_BYPASS_ATTEMPTS):
      O bot não tem saída para humano. Encerre educadamente.
      stage = failed
      response = "Entendido, obrigado pela atenção!"

    === REGRAS ===
    - NÃO explique o que você está fazendo
    - NÃO peça gestor diretamente ao bot (ele não entende)
    - NÃO envie mensagens longas — bots respondem a palavras-chave
    - Se o histórico mostrar que uma opção já foi tentada, tente outra
    """

    clinic_name: str = dspy.InputField(desc="Nome da clínica")
    conversation_history: str = dspy.InputField(desc="Histórico da conversa")
    latest_message: str = dspy.InputField(desc="Última resposta do bot")
    attempt_count: int = dspy.InputField(desc="Número de tentativas de bypass já feitas")
    max_attempts: int = dspy.InputField(desc="Máximo de tentativas antes de encerrar")

    reasoning: str = dspy.OutputField(desc="Raciocínio sobre qual opção tentar")
    response_message: str = dspy.OutputField(desc="Mensagem a enviar ao bot")
    conversation_stage: str = dspy.OutputField(
        desc="'handling_objection' se ainda tentando bypass, 'failed' se esgotado"
    )
    should_send_message: bool = dspy.OutputField(desc="Sempre True")


class MenuBotAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.respond = dspy.ChainOfThought(MenuBotSignature)

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
                "conversation_stage": "failed",
                "should_send_message": True,
                "reasoning": "Bypass esgotado — bot não tem saída para humano.",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
            }

        history_text = "\n".join(
            f"{'Agente' if t['role'] == 'agent' else 'Bot'}: {t['content']}"
            for t in conversation_history
        ) or "(sem histórico)"

        try:
            result = self.respond(
                clinic_name=clinic_name,
                conversation_history=history_text,
                latest_message=latest_message,
                attempt_count=attempt_count,
                max_attempts=MAX_BYPASS_ATTEMPTS,
            )

            stage = str(result.conversation_stage).strip().lower()
            if stage not in {"handling_objection", "failed"}:
                stage = "handling_objection"

            return {
                "response_message": str(result.response_message).strip(),
                "conversation_stage": stage,
                "should_send_message": True,
                "reasoning": str(result.reasoning).strip(),
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
            }

        except Exception as e:
            return {
                "response_message": "falar com atendente",
                "conversation_stage": "handling_objection",
                "should_send_message": True,
                "reasoning": f"Erro: {e}",
                "extracted_manager_contact": None,
                "extracted_manager_email": None,
                "extracted_manager_name": None,
            }
