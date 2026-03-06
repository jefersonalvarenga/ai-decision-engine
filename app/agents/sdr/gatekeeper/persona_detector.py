"""
Persona Detector - Classifica quem está respondendo no WhatsApp da clínica.

Roda uma única vez por conversa, na primeira resposta recebida da clínica.
O resultado é persistido no estado e repassado pelo n8n nas chamadas seguintes.

Personas:
  receptionist  — Recepcionista Real (alvo principal)
  menu_bot      — Bot de Menu (numerado ou estruturado)
  ai_assistant  — IA Conversacional (chatbot que simula humano)
  call_center   — Central de Atendimento terceirizada
  manager       — Gestor/Dono respondendo diretamente
  unknown       — Sinal insuficiente para classificar (default: tratar como receptionist)
"""

import dspy
from typing import Optional


class PersonaDetectorSignature(dspy.Signature):
    """
    Você analisa a primeira resposta de uma clínica no WhatsApp e classifica
    quem está do outro lado. Isso determina a estratégia da abordagem.

    === PERSONAS E SINAIS ===

    receptionist — Recepcionista humana real
    Sinais: menciona o próprio nome ("Aqui é a Juliana"), tom pessoal e casual,
    responde com linguagem natural, pode hesitar ou usar abreviações, fala como
    pessoa real. É a persona mais comum em clínicas independentes.
    Exemplos: "Olá! Aqui é a Tayná, em que posso ajudar?" / "Sim, boa tarde!"

    menu_bot — Bot de menu automatizado
    Sinais: resposta estruturada com opções numeradas ou com emojis de lista,
    nunca menciona nome pessoal, linguagem mecânica e padronizada, pode dizer
    "Selecione uma opção" ou "Digite 1 para X, 2 para Y", resposta idêntica
    para qualquer mensagem recebida.
    Exemplos: "Olá! Escolha uma opção:\n1. Agendar consulta\n2. Falar com atendente"

    ai_assistant — Inteligência Artificial conversacional
    Sinais: se identifica explicitamente como assistente virtual, IA ou chatbot
    ("Olá! Sou o assistente virtual da Clínica X"), OU tem gramática perfeita
    demais para WhatsApp, responde com estrutura completa e formal, nunca usa
    abreviações, oferece menu em linguagem natural com frases muito polidas,
    resposta instantânea em qualquer horário. Pode usar emojis de forma sistemática.
    Exemplos: "Olá! Sou a assistente virtual da clínica. Como posso te ajudar hoje? 😊"
              "Oi! Aqui é a IA da Clínica X. Posso te ajudar com agendamentos, informações..."

    call_center — Central de atendimento terceirizada
    Sinais: atendente menciona explicitamente "central de atendimento", "sou especialista
    de agendamento", "departamento", ou o número é um 0800. A atendente deixa claro
    que não tem acesso ao gestor — só faz agendamentos. Pode mencionar múltiplas
    "especialistas" ou transferências internas.
    Exemplos: "Olá! Falo da central de atendimento da clínica. Como posso ajudar?"
              "Aqui é a Vitória, especialista de agendamento. Em que posso ajudar?"

    manager — Gestor, dono ou responsável respondendo diretamente
    Sinais: se identifica explicitamente como dono, gestor, diretor ou responsável
    pela clínica. Comum em clínicas muito pequenas onde o dono atende o WhatsApp.
    Exemplos: "Sou eu mesmo o gestor" / "Aqui é o Dr. Carlos, sou o dono"
              "Sou a responsável pela clínica" / "Pode falar comigo, cuido de tudo aqui"

    unknown — Sinal insuficiente
    Use quando a resposta é muito curta ou ambígua para classificar com segurança.
    Exemplos: "Sim" / "Oi" / "Pois não?"
    Estratégia: tratar como receptionist (mais seguro).

    === REGRAS DE CLASSIFICAÇÃO ===

    1. Se a resposta menciona "assistente virtual", "IA", "inteligência artificial",
       "chatbot" → ai_assistant (independente de qualquer outro sinal).
    2. Se há lista numerada de opções ou estrutura de menu → menu_bot.
    3. Se menciona "central de atendimento", "especialista de agendamento", 0800 → call_center.
    4. Se se identifica como dono/gestor/responsável → manager.
    5. Se parece humano mas o sinal é fraco → unknown (não force receptionist).
    6. Em caso de dúvida entre ai_assistant e receptionist: prefira ai_assistant
       se a gramática for perfeita demais para WhatsApp informal.
    """

    clinic_name: str = dspy.InputField(
        desc="Nome da clínica contatada"
    )
    conversation_history: str = dspy.InputField(
        desc="Histórico da conversa até agora (incluindo a primeira mensagem do agente)"
    )
    latest_message: str = dspy.InputField(
        desc="Primeira resposta recebida da clínica — base principal para classificação"
    )

    reasoning: str = dspy.OutputField(
        desc="Análise dos sinais encontrados na mensagem que levaram à classificação"
    )
    persona: str = dspy.OutputField(
        desc="Persona detectada: receptionist | menu_bot | ai_assistant | call_center | manager | unknown"
    )
    confidence: str = dspy.OutputField(
        desc="Confiança na classificação: high | medium | low"
    )
    key_signal: str = dspy.OutputField(
        desc="Trecho ou característica da mensagem que foi o sinal mais forte para a classificação"
    )


_VALID_PERSONAS = {"receptionist", "menu_bot", "ai_assistant", "call_center", "manager", "unknown"}


class PersonaDetector(dspy.Module):
    """
    Classifica a persona do contato na clínica.

    Deve ser chamado apenas uma vez por conversa — na primeira resposta recebida.
    O resultado é repassado pelo n8n como `detected_persona` nas chamadas seguintes,
    evitando re-classificação desnecessária.
    """

    def __init__(self):
        super().__init__()
        self.classify = dspy.ChainOfThought(PersonaDetectorSignature)

    def forward(
        self,
        clinic_name: str,
        conversation_history: list,
        latest_message: str,
    ) -> dict:
        """
        Classifica a persona com base na primeira resposta da clínica.

        Returns:
            dict com persona, confidence, key_signal, reasoning
        """
        history_text = "\n".join(
            f"{'Agente' if t['role'] == 'agent' else 'Clínica'}: {t['content']}"
            for t in conversation_history
        ) or "(sem histórico)"

        try:
            result = self.classify(
                clinic_name=clinic_name,
                conversation_history=history_text,
                latest_message=latest_message,
            )

            persona = str(result.persona).strip().lower()
            if persona not in _VALID_PERSONAS:
                persona = "unknown"

            confidence = str(result.confidence).strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "low"

            return {
                "persona": persona,
                "confidence": confidence,
                "key_signal": str(result.key_signal).strip(),
                "reasoning": str(result.reasoning).strip(),
            }

        except Exception as e:
            return {
                "persona": "unknown",
                "confidence": "low",
                "key_signal": "",
                "reasoning": f"Erro na classificação: {e}",
            }
