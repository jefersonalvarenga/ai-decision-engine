import dspy
from .signatures import CriticSignature

class CriticAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        # Usamos Predict em vez de TypedPredictor para ter mais controle manual se necessário
        self.process = dspy.Predict(CriticSignature)

    def forward(self, state):
        res = self.process(
            generated_copy=state.get("generated_copy"),
            analyst_diagnosis=state.get("analyst_diagnosis")
        )
        
        # Lógica de Ouro: Se o feedback for positivo ou contiver "adequada", "boa" ou "aprovada"
        # e o modelo se confundir no booleano, nós forçamos o True.
        feedback = str(res.critic_feedback).lower()
        approved = str(res.is_approved).lower() == "true"
        
        # Se o feedback parece positivo mas o booleano veio False, corrigimos:
        if "adequada" in feedback or "parabéns" in feedback or "excelente" in feedback:
            approved = True
            
        return {
            "is_approved": approved,
            "critic_feedback": str(res.critic_feedback),
            "revision_count": 1
        }