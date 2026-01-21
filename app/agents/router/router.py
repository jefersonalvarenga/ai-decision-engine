"""
EasyScale Router Agent
Standard: Enterprise-Grade Multilanguage Routing
"""

import os
import json
import operator
from typing import TypedDict, List, Annotated, Literal
from enum import Enum

import dspy
from langgraph.graph import StateGraph, END

# ============================================================================
# INTENT DEFINITIONS
# ============================================================================

class IntentType(str, Enum):
    SESSION_START = "SESSION_START"
    SESSION_CLOSURE = "SESSION_CLOSURE"
    SERVICE_SCHEDULING = "SERVICE_SCHEDULING"
    SERVICE_RESCHEDULING = "SERVICE_RESCHEDULING"
    SERVICE_CANCELLATION = "SERVICE_CANCELLATION"
    MEDICAL_ASSESSMENT = "MEDICAL_ASSESSMENT"
    PROCEDURE_INQUIRY = "PROCEDURE_INQUIRY"
    AD_CONVERSION = "AD_CONVERSION"
    ORGANIC_INQUIRY = "ORGANIC_INQUIRY"
    OFFER_CONVERSION = "OFFER_CONVERSION"
    REENGAGEMENT_RECOVERY = "REENGAGEMENT_RECOVERY"
    GENERAL_INFO = "GENERAL_INFO"
    IMAGE_ASSESSMENT = "IMAGE_ASSESSMENT"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    UNCLASSIFIED = "UNCLASSIFIED" # Adicionado para bater com a lógica

# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    context: dict
    latest_message: str
    intent_queue: Annotated[List[str], operator.add]
    final_response: str
    urgency_score: int
    reasoning: str

# ============================================================================
# DSPY SIGNATURE
# ============================================================================

class RouterSignature(dspy.Signature):
    """
    Global Intent Classifier for Aesthetic Clinics.
    Interpret the patient_message based on the input_language and map it to 
    standardized English Intent Categories.
    """

    context_json = dspy.InputField(desc="JSON string with patient history and profile.")
    input_language = dspy.InputField(desc="The language of the message (e.g., 'Brazilian Portuguese').")
    patient_message = dspy.InputField(desc="The raw message from the patient.")

    intents: List[str] = dspy.OutputField(
        desc=(
            "List of detected intents. STRICTLY USE ONLY: "
            "SESSION_START, SESSION_CLOSURE, SERVICE_SCHEDULING, SERVICE_RESCHEDULING, "
            "SERVICE_CANCELLATION, MEDICAL_ASSESSMENT, PROCEDURE_INQUIRY, AD_CONVERSION, "
            "ORGANIC_INQUIRY, OFFER_CONVERSION, REENGAGEMENT_RECOVERY, GENERAL_INFO, "
            "IMAGE_ASSESSMENT, HUMAN_ESCALATION, UNCLASSIFIED. "
            "Rules: 1. Multiple intents allowed. 2. Prioritize MEDICAL_ASSESSMENT. "
            "3. Use UNCLASSIFIED if ambiguous."
        )
    )

    urgency_score: int = dspy.OutputField(desc="Score 1-5 based on clinical risk. 5 is critical.")
    reasoning: str = dspy.OutputField(desc="Technical rationale in English.")

# ============================================================================
# MODULE & NODE
# ============================================================================

class RouterModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.classifier = dspy.ChainOfThought(RouterSignature)

    def forward(self, context_json: str, patient_message: str):
        input_lang = os.getenv("INPUT_LANGUAGE", "Brazilian Portuguese")
        return self.classifier(
            context_json=context_json,
            input_language=input_lang,
            patient_message=patient_message
        )

# MOVIDO PARA FORA DA CLASSE
def router_node(state: AgentState) -> AgentState:
    router = RouterModule()

    prediction = router(
        context_json=json.dumps(state["context"], ensure_ascii=False),
        patient_message=state["latest_message"]
    )

    # Pegamos o que a IA devolveu
    raw_output = prediction.intents
    
    # 1. Normalização para Lista
    if isinstance(raw_output, str):
        cleaned = raw_output.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
        intent_list = [i.strip() for i in cleaned.split(",")]
    else:
        intent_list = raw_output

    # 2. Validação contra o Enum
    valid_values = {item.value for item in IntentType}
    
    # Mapeamento e Limpeza
    final_intents = [
        i if i in valid_values else IntentType.UNCLASSIFIED.value 
        for i in intent_list
    ]

    if not final_intents:
        final_intents = [IntentType.UNCLASSIFIED.value]

    return {
        "intent_queue": final_intents,
        "urgency_score": prediction.urgency_score,
        "reasoning": prediction.rationale,
    }