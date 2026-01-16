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