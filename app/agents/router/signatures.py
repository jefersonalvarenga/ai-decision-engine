import dspy
from typing import List

class RouterSignature(dspy.Signature):
    """Classify patient intent and determine the best route."""
    context = dspy.InputField(desc="Patient history and clinic data")
    latest_message = dspy.InputField(desc="The new message from WhatsApp")
    
    intent_queue = dspy.OutputField(desc="List of detected intents (e.g., BOOKING, DOUBT, COMPLAINT)")
    urgency_score = dspy.OutputField(desc="1 to 5 scale of urgency")
    reasoning = dspy.OutputField(desc="Brief explanation of the routing decision")
    routed_to = dspy.OutputField(desc="Destination: 'scheduler', 'support', or 'human_urgent'")
    final_response = dspy.OutputField(desc="A polite acknowledgment message in pt-BR")