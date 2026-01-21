import dspy
from typing import List

class RouterSignature(dspy.Signature):
    """Classify patient intent and determine the best route."""
    context = dspy.InputField(desc="Patient history and clinic data")
    latest_message = dspy.InputField(desc="The new message from WhatsApp")
    
    intents: List[str] = dspy.OutputField(
        desc=(
            "List of intents. Choose ONLY from: [SESSION_START, SESSION_CLOSURE, "
            "SERVICE_SCHEDULING, SERVICE_RESCHEDULING, SERVICE_CANCELLATION, "
            "MEDICAL_ASSESSMENT, PROCEDURE_INQUIRY, AD_CONVERSION, ORGANIC_INQUIRY, "
            "OFFER_CONVERSION, REENGAGEMENT_RECOVERY, GENERAL_INFO, IMAGE_ASSESSMENT, "
            "HUMAN_ESCALATION, UNCLASSIFIED].\n"
            "Example output: ['OFFER_CONVERSION', 'PROCEDURE_INQUIRY']"
        )
    )
    

    urgency_score = dspy.OutputField(desc="1 to 5 scale of urgency")
    reasoning = dspy.OutputField(desc="Brief explanation of the routing decision")
    routed_to = dspy.OutputField(desc="Destination: 'scheduler', 'support', or 'human_urgent'")
    final_response = dspy.OutputField(desc="A polite acknowledgment message in pt-BR")