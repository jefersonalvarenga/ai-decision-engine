import dspy

class AnalystSignature(dspy.Signature):
    """
    Analise o histórico da conversa e o perfil do paciente para identificar 
    o motivo real do sumiço (ghosting) e os gatilhos emocionais.
    """
    customer_name = dspy.InputField(desc="Nome do lead")
    ad_source = dspy.InputField(desc="Origem do anúncio")
    psychographic_profile = dspy.InputField(desc="Idade, interesses e dores")
    conversation_history = dspy.InputField(desc="Últimas mensagens trocadas")
    
    analyst_diagnosis = dspy.OutputField(desc="Diagnóstico estratégico em português")

class StrategistSignature(dspy.Signature):
    """
    Escolha a melhor estratégia de re-engajamento (PROVA_SOCIAL, EDUCACIONAL, OFERTA_DIRETA ou CURIOSIDADE).
    """
    analyst_diagnosis = dspy.InputField()
    selected_strategy = dspy.OutputField(desc="Apenas o nome da estratégia escolhida")

class CopywriterSignature(dspy.Signature):
    """
    Escreva uma mensagem de WhatsApp curta, humana e altamente persuasiva.
    REGRAS: 
    - No máximo 2 ou 3 parágrafos curtos.
    - Tom de conversa entre amigos, sem formalidades.
    - Se o problema for medo, mencione conforto e anestesia de forma leve.
    - NÃO use hashtags ou termos como 'Prezada'.
    """
    selected_strategy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    generated_copy = dspy.OutputField(desc="Mensagem final pronta para enviar")

class CriticSignature(dspy.Signature):
    """
    Avalie a qualidade da mensagem de re-engajamento.
    Sua única função é barrar mensagens agressivas, formais demais ou com erros médicos.
    
    REGRA DE OURO: Se a mensagem for amigável, curta e tratar Mariana pelo nome, 
    você DEVE definir is_approved como True. 
    Não tente melhorar o que já está bom.
    """
    generated_copy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    
    is_approved = dspy.OutputField(desc="REGRAS: Apenas 'True' ou 'False'")
    critic_feedback = dspy.OutputField(desc="Justificativa da sua decisão")