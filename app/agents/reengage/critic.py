import dspy
from .signatures import CriticSignature

class CriticAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        # Mudamos para ChainOfThought para garantir que a IA analise 
        # as "Regras de Ouro" antes de aprovar.
        self.critique = dspy.ChainOfThought(CriticSignature)
    
    def forward(self, state: dict):
        """
        Acts as a Clinical Director to review the generated copy.
        Checks for compliance, empathy, and medical safety rules.
        """
        # Executa a crítica baseada na copy gerada e no diagnóstico inicial
        result = self.critique(
            generated_copy=state['generated_copy'], 
            analyst_diagnosis=state['analyst_diagnosis']
        )
        
        # Retornamos o feedback e o booleano de aprovação para o Grafo
        return {
            "critic_feedback": result.critic_feedback,
            "is_approved": result.is_approved,
            "revision_count": 1 # O operator.add no State vai somar este valor
        }