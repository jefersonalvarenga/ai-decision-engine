import dspy
from .signatures import StrategistSignature

class StrategistAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.select_strategy = dspy.Predict(StrategistSignature)
    
    def forward(self, state: dict):
        """
        Receives the full graph state. 
        Expects 'analyst_diagnosis' to be populated by the previous node.
        """
        # Execute the strategy selection logic
        result = self.select_strategy(
            analyst_diagnosis=state['analyst_diagnosis']
        )
        
        # Returns a dictionary to update the LangGraph state
        return {
            "selected_strategy": str(result.selected_strategy)
        }