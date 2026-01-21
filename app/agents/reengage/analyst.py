import dspy
from .signatures import AnalystSignature

class AnalystAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.process = dspy.Predict(AnalystSignature)

    def forward(self, state):
        res = self.process(
            customer_name=state.get("lead_name"),
            ad_source=state.get("ad_source"),
            psychographic_profile=state.get("psychographic_profile"),
            conversation_history=state.get("conversation_history")
        )
        # O retorno PRECISA ser um dicionário
        return {"analyst_diagnosis": str(res.analyst_diagnosis)}