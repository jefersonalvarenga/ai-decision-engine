import dspy
from .signatures import AnalystSignature

class AnalystAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.analyze = dspy.Predict(AnalystSignature)
    
    def forward(self, state):
        return self.analyze(
            lead_name=state['lead_name'],
            ad_source=state['ad_source'],
            psychographic_profile=str(state['psychographic_profile']),
            conversation_history=str(state['conversation_history'])
        ).analyst_diagnosis