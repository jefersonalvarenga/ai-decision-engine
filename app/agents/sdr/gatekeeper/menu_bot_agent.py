"""
Menu Bot Agent - Tenta bypassar bots de menu para chegar em um humano.
Usa DSPy para decidir a melhor abordagem com base no menu recebido.
"""

import dspy
from .utils import safe_str


class MenuBotSignature(dspy.Signature):
    """
    Você é um SDR tentando bypassar um bot de menu de uma clínica médica.
    Seu único objetivo é chegar em um atendente humano que possa te passar
    o contato do gestor/responsável pela clínica.

    === CONTEXTO ===
    O bot de menu responde automaticamente com opções numeradas ou estruturadas.
    Você precisa analisar o menu e encontrar a melhor forma de chegar em um humano.

    === ESTRATÉGIA ===
    1. Analise as opções disponíveis no menu — prefira opções como "falar com atendente",
       "atendimento humano", "falar com um humano", ou similares.
    2. Se houver opção numerada clara para atendente humano, use o número (ex: "2").
    3. Se não houver opção óbvia, tente a que mais se aproxima de atendimento geral.
    4. Antes de responder, leia o histórico inteiro:
       - Veja quantas vezes [Agente] já respondeu ao bot
       - Verifique se o [Bot] voltou com o mesmo menu após cada tentativa
       - Se o [Bot] repetiu o mesmo menu após suas tentativas, significa que não
         há caminho para um humano — encerre com stage=menu_blocked.
    5. Só tente uma nova abordagem se o histórico mostrar que ainda não tentou ou tentou apenas uma vez.

    === STAGES ===
    - requesting: ainda tentando bypassar o bot para chegar em um humano
    - menu_blocked: bot ignorou suas tentativas, não há caminho para humano
    """

    clinic_name: str = dspy.InputField(desc="Nome da clínica")
    conversation_history: str = dspy.InputField(desc="Histórico da conversa até agora — use para avaliar quantas tentativas já foram feitas e se o bot está ignorando suas respostas")
    latest_message: str = dspy.InputField(desc="Última mensagem do bot de menu")

    reasoning: str = dspy.OutputField(desc="Análise do menu e justificativa da abordagem escolhida")
    response_message: str = dspy.OutputField(desc="Mensagem a enviar. Se tentando bypass: opção do menu (ex: '2', 'falar com atendente'). Se encerrando (menu_blocked): mensagem curta de despedida educada.")
    conversation_stage: str = dspy.OutputField(desc="Stage: requesting | menu_blocked")
    should_send_message: str = dspy.OutputField(desc="sempre true")


class MenuBotAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.process = dspy.ChainOfThought(MenuBotSignature)

    def forward(
        self,
        clinic_name: str,
        conversation_history: list,
        latest_message: str,
    ) -> dict:
        history_text = "\n".join(
            f"{'[Agente]' if t['role'] == 'agent' else '[Bot]'}: {t['content']}"
            for t in (conversation_history or [])
        ) or "(sem histórico)"

        result = self.process(
            clinic_name=clinic_name,
            conversation_history=history_text,
            latest_message=latest_message,
        )

        stage = safe_str(result.conversation_stage, "requesting").lower().strip()
        if stage not in ("requesting", "menu_blocked"):
            stage = "requesting"

        should_send = safe_str(result.should_send_message, "true").lower().strip() == "true"
        response_message = safe_str(result.response_message, "").strip()

        if not response_message or response_message.lower() == "null":
            should_send = False
            response_message = ""

        return {
            "reasoning": safe_str(result.reasoning, ""),
            "response_message": response_message,
            "conversation_stage": stage,
            "should_send_message": should_send,
            "extracted_manager_contact": None,
            "extracted_manager_email": None,
            "extracted_manager_name": None,
        }
