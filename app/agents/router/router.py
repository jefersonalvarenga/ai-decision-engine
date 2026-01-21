"""
EasyScale Router Agent
Standard: Enterprise-Grade Multilanguage Routing
"""

import os
import json
import operator
import dspy
from typing import TypedDict, List, Annotated, Literal
from enum import Enum
from signature import RouterSignature, IntentType
from langgraph.graph import StateGraph, END

# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    latest_incoming: str
    history: List[str]
    intake_status: str       # 'in_progress' ou 'completed'
    schedule_status: str     # 'in_progress' ou 'idle'
    reschedule_status: str   # 'in_progress' ou 'idle'
    cancel_status: str       # 'in_progress' ou 'idle'
    language: str     # 'PT-BR' ou EN-US
    
    # Resultados do Router
    intentions: Annotated[List[str], operator.add]
    reasoning: str
    confidence: float

# ============================================================================
# MODULE & NODE
# ============================================================================

class RouterModule(dspy.Module):

    """
    The core DSPy module that uses ChainOfThought to classify the patient's intentions
    based on the highly contextualized RouterSignature.
    """
    def __init__(self):
        super().__init__()
        self.classifier = dspy.ChainOfThought(RouterSignature)

    def forward(self, latest_incoming: str, history: str, intake_status: str, schedule_status: str, reschedule_status: str, cancel_status: str, language: str) -> Dict[str, Any]:
        input_lang = os.getenv("INPUT_LANGUAGE", "PT-BR")
        return self.classifier(
            latest_incoming=latest_incoming,
            history=history,
            intake_status=intake_status,
            schedule_status=schedule_status,
            reschedule_status=reschedule_status,
            cancel_status=cancel_status,
            language=language
        )

# ============================================================================
# ROUTER AGENT IMPLEMENTATION (The n8n Mapper)
# ============================================================================

class RouterAgent:
    """
    A wrapper class that uses RouterModule to get the prediction and maps 
    the output to the required n8n JSON format.
    """
    def __init__(self):
        self.router_module = RouterModule()

    def forward(self, latest_incoming: str, history: str, intake_status: str, schedule_status: str, reschedule_status: str, cancel_status: str, language: str) -> Dict[str, Any]:
        """
        Executes the DSPy prediction and formats the result into the required n8n JSON structure.
        """

        # 1. Pré-processar o histórico de List[Dict] para String (formato esperado pelo LLM)
        # O LLM precisa de uma string formatada para contexto
        history_str = "\n".join([f"{item.get('role', 'System')}: {item.get('content', '')}" for item in history])

        
        # 2. Execute the DSPy prediction using the RouterModule
        prediction = self.router_module.forward(
            latest_incoming=latest_incoming,
            history=history,
            intake_status=intake_status,
            schedule_status=schedule_status,
            reschedule_status=reschedule_status,
            cancel_status=cancel_status,
            language=language
        )
        
        # 3. Map the DSPy output to the final JSON structure
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Ensure confidence is a float, with fallback
        try:
            confidence_value = float(prediction.confidence)
        except (ValueError, TypeError):
            confidence_value = 0.0

        # 4. Validate and clean intentions_list using IntentType Enum
        valid_intents = {item.value for item in IntentType}
        
        intentions_list = prediction.intentions_list
        
        if not isinstance(intentions_list, list):
            # Fallback: se o LLM retornar uma string, tentamos dividir por vírgula
            if isinstance(intentions_list, str):
                intentions_list = [i.strip() for i in intentions_list.split(',') if i.strip()]
            else:
                intentions_list = []
        
        # Filtra apenas as intenções que são valores válidos do nosso Enum
        cleaned_intentions = [
            intent for intent in intentions_list 
            if intent in valid_intents
        ]
        
        # Garante que UNCLASSIFIED seja o fallback se a lista estiver vazia
        if not cleaned_intentions:
            cleaned_intentions = [IntentType.UNCLASSIFIED.value]

        # 4. Final JSON Output (n8n format)
        output_json = {
            "agent": "router",
            "patient_intention": {
                "value": cleaned_intentions,
                "reasoning": prediction.reasoning,
                "confidence": confidence_value
            },
            "data": {
                "version": "1.0.0",
                "timestamp": timestamp
            }
        }
        
        return output_json