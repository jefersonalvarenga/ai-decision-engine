import dspy
import os
from .state import AgentState

# 1. Configuração do Modelo (LM)
# O DSPy centraliza a inteligência aqui. 
# Você pode trocar para Claude ou Llama mudando apenas esta linha.
turbo = dspy.OpenAI(model='gpt-4o-mini', max_tokens=1000)
dspy.settings.configure(lm=turbo)

# 2. Definição da Assinatura (A Tarefa)
class LeadAnalysisSignature(dspy.Signature):
    """
    Analyze the conversation history and patient profile.
    Identify:
    1. Why the lead stopped responding (Ghosting reason).
    2. Current temperature (Cold, Warm, Hot).
    3. Main psychological triggers identified.
    Provide the diagnosis in English.
    """
    
    lead_name = dspy.InputField()
    ad_source = dspy.InputField()
    psychographic_profile = dspy.InputField(desc="Patient's age, interests, and pain points")
    conversation_history = dspy.InputField(desc="Last exchanges between the clinic and the patient")
    
    analyst_diagnosis = dspy.OutputField(desc="Strategic diagnosis of the current lead state")

# 3. O Módulo (O "Agente" propriamente dito)
class AnalystAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        # Predictor simples. No futuro, podemos usar ChainOfThought para mais precisão.
        self.analyze = dspy.Predict(LeadAnalysisSignature)
    
    def forward(self, state: AgentState):
        # Executa a inferência usando os dados que vieram do LangGraph State
        result = self.analyze(
            lead_name=state['lead_name'],
            ad_source=state['ad_source'],
            psychographic_profile=str(state['psychographic_profile']),
            conversation_history=str(state['conversation_history'])
        )
        return result.analyst_diagnosis

class StrategistSignature(dspy.Signature):
    """
    Based on the Analyst Diagnosis, select the best re-engagement strategy.
    Options: 
    - SOCIAL_PROOF: Use patient testimonials related to the lead's pain.
    - EDUCATION: Send a tip or exercise to help with their specific goal.
    - DIRECT_OFFER: A limited-time discount or exclusive consultation.
    - CURIOSITY: Ask a specific question about their progress.
    
    Output the selected strategy name and a brief rationale in English.
    """
    analyst_diagnosis = dspy.InputField()
    selected_strategy = dspy.OutputField(desc="Name of the chosen strategy")
    rationale = dspy.OutputField(desc="Why this strategy fits the lead state")

class StrategistAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.select_strategy = dspy.Predict(StrategistSignature)
    
    def forward(self, diagnosis: str):
        result = self.select_strategy(analyst_diagnosis=diagnosis)
        return result.selected_strategy, result.rationale

class CopywriterSignature(dspy.Signature):
    """
    Write a persuasive WhatsApp message in Portuguese (pt-BR).
    Use the strategy and diagnosis provided.
    The message must be friendly, professional, and focus on the patient's pain/goal.
    Do not use hashtags. Keep it concise.
    """
    selected_strategy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    target_language = dspy.InputField()
    
    generated_copy = dspy.OutputField(desc="The final WhatsApp message in Portuguese")

class CopywriterAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.write = dspy.Predict(CopywriterSignature)
    
    def forward(self, strategy: str, diagnosis: str, language: str):
        result = self.write(
            selected_strategy=strategy, 
            analyst_diagnosis=diagnosis,
            target_language=language
        )
        return result.generated_copy

class CriticSignature(dspy.Signature):
    """
    Atue como um Diretor Clínico e Especialista em Compliance.
    Analise a mensagem de WhatsApp (copy) gerada.
    
    Critérios de Rejeição:
    1. Promessa de cura garantida ou resultados milagrosos.
    2. Tom excessivamente agressivo de vendas.
    3. Linguagem médica muito técnica que o paciente não entenda.
    4. Falta de empatia com a dor relatada.

    Forneça o feedback detalhado e o status de aprovação.
    """
    generated_copy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    
    critic_feedback = dspy.OutputField(desc="Explicação do porquê foi aprovado ou reprovado")
    is_approved = dspy.OutputField(desc="Aprovação final (True ou False)", bool=True)

class CriticAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.critique = dspy.Predict(CriticSignature)
    
    def forward(self, copy: str, diagnosis: str):
        result = self.critique(generated_copy=copy, analyst_diagnosis=diagnosis)
        return result.critic_feedback, result.is_approved