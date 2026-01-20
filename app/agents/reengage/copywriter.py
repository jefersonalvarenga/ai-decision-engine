import dspy
from .signatures import CopywriterSignature

class CopywriterAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        # Para escrita criativa, o Predict funciona bem. 
        # Se quiser mensagens mais elaboradas, o ChainOfThought é uma opção.
        self.write = dspy.Predict(CopywriterSignature)
    
    def forward(self, state: dict):
        """
        Receives the graph state and generates a persuasive message.
        Uses the 'selected_strategy' and 'analyst_diagnosis' to craft the copy.
        """
        # Execute the writing logic
        result = self.write(
            selected_strategy=state['selected_strategy'], 
            analyst_diagnosis=state['analyst_diagnosis']
        )
        
        # Returns a dictionary to update the 'generated_copy' key in the state
        return {
            "generated_copy": result.generated_copy
        }