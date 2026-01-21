import dspy
from enum import Enum
from typing import List # Adicionando List para o OutputField

# ============================================================================
# INTENT DEFINITIONS (ENUM)
# ============================================================================

class IntentType(str, Enum):
    """
    Defines the set of valid intentions (domains/agents) that the router can activate.
    """
    SESSION_START = "SESSION_START"
    SESSION_CLOSURE = "SESSION_CLOSURE"
    SERVICE_SCHEDULING = "SERVICE_SCHEDULING"
    SERVICE_RESCHEDULING = "SERVICE_RESCHEDULING"
    SERVICE_CANCELLATION = "SERVICE_CANCELLATION"
    INTAKE = "INTAKE"
    MEDICAL_ASSESSMENT = "MEDICAL_ASSESSMENT"
    PROCEDURE_INQUIRY = "PROCEDURE_INQUIRY"
    AD_CONVERSION = "AD_CONVERSION"
    ORGANIC_INQUIRY = "ORGANIC_INQUIRY"
    OFFER_CONVERSION = "OFFER_CONVERSION"
    REENGAGEMENT_RECOVERY = "REENGAGEMENT_RECOVERY"
    GENERAL_INFO = "GENERAL_INFO"
    IMAGE_ASSESSMENT = "IMAGE_ASSESSMENT"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    UNCLASSIFIED = "UNCLASSIFIED"

class RouterSignature(dspy.Signature):
    """
    You are a router agent responsible for identifying which specialized agents (domains) need to be activated to fully address the patient's current message and needs in a medical conversational flow via WhatsApp.
    
    CRITICAL CONTEXT: This system is a high-conversion sales funnel for a **high-end aesthetic clinic** (private pay only). The primary goal is to convert leads (often from Instagram ads) into paying patients for **high-cost procedures**. The router must prioritize intentions that indicate a strong purchase intent (e.g., SERVICE_SCHEDULING, PROCEDURE_INQUIRY, AD_CONVERSION) and handle all inquiries with a premium, conversion-focused approach.

    Routing Instructions:
    1. Focus on the most recent message (`latest_incoming`). Use `history` only for context.
    2. Intentions Enumerators: The list of valid intentions is defined by the IntentType Enum.
        - 'SESSION_START': The patient initiates the conversation (e.g., "Hello", "Good morning").
        - 'SESSION_CLOSURE': The patient explicitly ends the conversation (e.g., "Thank you, bye", "I'm done").
        - 'SERVICE_SCHEDULING': The patient expresses interest in booking a service or appointment, OR the patient is actively discussing scheduling details (e.g., "When can I do the procedure?", "Is Tuesday the only time?", "I'm doing pilates at that time"). This activates the specialized Scheduling Agent.
        - 'SERVICE_RESCHEDULING': The patient requests to change an existing appointment. This activates the specialized Rescheduling Agent.
        - 'SERVICE_CANCELLATION': The patient requests to cancel an existing appointment. This activates the specialized Cancellation Agent.
        - 'INTAKE': The patient is responding to clinical probes (intake), providing medical history relevant to aesthetic procedures. This activates the specialized Intake Assessment Agent.
        - 'MEDICAL_ASSESSMENT': The patient is asking a spontaneous medical question, often related to the safety or efficacy of aesthetic treatments. This activates the specialized Medical Assessment Agent.
        - 'PROCEDURE_INQUIRY': The patient asks about a specific aesthetic procedure, treatment, or service offered (e.g., "How much is a facelift?", "Tell me about the recovery for liposuction"). This is a high-priority conversion signal and activates the specialized Procedure Inquiry Agent.
        - 'AD_CONVERSION': The patient mentions or refers to a specific advertisement or campaign. This is a high-priority conversion signal.
        - 'ORGANIC_INQUIRY': The patient is making a general, non-ad-related inquiry about services.
        - 'OFFER_CONVERSION': The patient is responding to a specific promotional offer. This is a high-priority conversion signal.
        - 'REENGAGEMENT_RECOVERY': The patient is responding to a re-engagement message from the agent after a period of inactivity.
        - 'GENERAL_INFO': The patient asks for institutional or general information (e.g., address, opening hours, general pricing). Given the high-cost context, the response should be premium and immediately attempt to guide the patient back to a conversion-focused intention (e.g., SERVICE_SCHEDULING or PROCEDURE_INQUIRY). This activates the specialized General Info Agent.
        - 'IMAGE_ASSESSMENT': The patient sends an image or indicates a need for image analysis (e.g., "I'm sending a picture of my rash").
        - 'HUMAN_ESCALATION': The patient explicitly requests to speak to a human agent (e.g., "I want to talk to a person"). This is a high-priority signal.
        - 'UNCLASSIFIED': None of the above intentions clearly represent the message content.
    
    4. Analyze the entire phrase and include ALL applicable intentions. This is CRITICAL, as including all intentions ensures that ALL necessary specialized agents are activated to fully address the patient's needs and questions. Failing to include an intention will prevent the corresponding agent from being activated.

    Confidence Notes (Suggestion):
    - 0.90–1.00: clear and explicit
    - 0.60–0.89: probable with some ambiguity
    - <0.60: uncertain / weak context
    """

    # Input Fields
    latest_incoming = dspy.InputField(desc="The most recent message received from the patient.")
    history = dspy.InputField(desc="The full conversation history, formatted as a string (use only if context is needed).")
    intake_status = dspy.InputField(desc="The current status of the clinical intake (e.g., 'in_progress', 'completed').")
    schedule_status = dspy.InputField(desc="The current status of the service scheduling (e.g., 'in_progress', 'pending').")
    reschedule_status = dspy.InputField(desc="The current status of the service rescheduling (e.g., 'in_progress', 'pending').")
    cancel_status = dspy.InputField(desc="The current status of the service canceling (e.g., 'in_progress', 'pending').")
    language = dspy.InputField(desc="The patient's language (e.g., 'pt-BR', 'en-US').")

    # Output Fields
    intentions = dspy.OutputField(desc="List of identified patient intentions (e.g., ['SERVICE_SCHEDULING', 'AD_CONVERSION']).")
    reasoning = dspy.OutputField(desc="Short and objective phrase (max 300 chars) explaining the routing decision.")
    confidence = dspy.OutputField(desc="Confidence level in the decision (0.0 to 1.0).")