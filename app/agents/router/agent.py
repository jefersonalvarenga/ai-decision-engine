"""
EasyScale Router Agent Module

This module implements the main routing logic for the EasyScale aesthetic clinic
customer service system. It uses DSPy for intent classification and LangGraph
for orchestrating the agent workflow.

The router is optimized to interpret Brazilian Portuguese (PT-BR) messages
from WhatsApp patients and route them to specialized agents.
"""

import operator
from typing import TypedDict, List, Annotated, Literal
from enum import Enum

import dspy
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field


# ============================================================================
# INTENT DEFINITIONS
# ============================================================================

class IntentType(str, Enum):
    """Available intent types for patient message classification."""

    # SESSION MANAGEMENT
    SESSION_START = "SESSION_START"      # Greetings, "Hi", introductions.
    SESSION_CLOSURE = "SESSION_CLOSURE"  # Finalizing chat after a completed action (farewells).

    # APPOINTMENT MANAGEMENT
    SERVICE_SCHEDULING = "SERVICE_SCHEDULING"      # Booking new appointments.
    SERVICE_RESCHEDULING = "SERVICE_RESCHEDULING"  # Changing existing appointments.
    SERVICE_CANCELLATION = "SERVICE_CANCELLATION"  # Cancellation existing appointments.
    
    # CLINICAL & TECHNICAL
    MEDICAL_ASSESSMENT = "MEDICAL_ASSESSMENT" # Health concerns, complications, symptoms, or urgency.
    PROCEDURE_INQUIRY = "PROCEDURE_INQUIRY"   # Technical questions about how it works, pain, or recovery.

    # SALES & CONVERSION (The Funnel)
    AD_CONVERSION = "AD_CONVERSION"           # Direct response to external ads (IG/FB/TikTok).
    ORGANIC_INQUIRY = "ORGANIC_INQUIRY"       # Organic lead asking about general services/offers.
    OFFER_CONVERSION = "OFFER_CONVERSION"     # Leads responding to active clinic-outbound campaigns.
    REENGAGEMENT_RECOVERY = "REENGAGEMENT_RECOVERY" # Successful response to the "Cold Lead" workflow.

    # SYSTEM & TOOLS
    GENERAL_INFO = "GENERAL_INFO"         # Clinic hours, address, parking, etc.
    IMAGE_ASSESSMENT = "IMAGE_ASSESSMENT" # When a patient sends a photo for visual analysis.
    HUMAN_ESCALATION = "HUMAN_ESCALATION" # Requesting a human agent or manager (HITL).


# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """
    State container for the EasyScale agent workflow.

    This state is passed between nodes in the LangGraph and accumulates
    information throughout the conversation flow.
    """

    context: dict
    """
    JSON context from the view_context_hydration view in Supabase.
    Contains patient history, active_items, behavioral_profile, etc.
    """

    latest_message: str
    """Current WhatsApp message from the patient (in PT-BR)."""

    intent_queue: Annotated[List[str], operator.add]
    """
    Ordered list of detected intents to be processed.
    Uses operator.add to allow multiple nodes to append intents.
    """

    final_response: str
    """Accumulated response text to be sent back to the patient."""

    urgency_score: int
    """Urgency score from 1-5, where 5 indicates immediate medical attention."""

    reasoning: str
    """Internal reasoning for the routing decision (in English, for logging)."""


# ============================================================================
# DSPY SIGNATURE
# ============================================================================

class RouterSignature(dspy.Signature):
    """
    Global Intent Classifier for Aesthetic Clinics.
    The system must interpret the patient_message (in the language specified by ENV)
    and map it to the standardized English Intent Categories.
    """

    context_json = dspy.InputField(desc="JSON string with patient history, last interaction, and profile.")
    input_language = dspy.InputField(desc="The language of the patient_message (e.g., 'Portuguese', 'English', 'Spanish').")
    patient_message = dspy.InputField(desc="The raw message received from the patient via WhatsApp/Messaging.")

    intents = dspy.OutputField(
        desc=(
            "List of detected intents based on the following mapping:\n"
            "1. Return MULTIPLE intents if the message contains multiple requests.\n"
            "2. Always prioritize MEDICAL_ASSESSMENT for safety.\n"
            "3. Always include SESSION_START for new conversations or returns after a long pause.\n\n"
            
            "Standardized Categories:\n"
            "- SESSION_START: Greetings, introductory phrases, or first contact.\n"
            "- SESSION_CLOSURE: Farewells, thank yous, and closing of the cycle.\n"
            "- SERVICE_SCHEDULING: Expressed desire to book a new appointment.\n"
            "- SERVICE_RESCHEDULING: Requests to change existing appointment times/dates.\n"
            "- SERVICE_CANCELLATION: Requests to cancel or stop a scheduled procedure.\n"
            "- MEDICAL_ASSESSMENT: Health concerns, complications, symptoms, or emergency signs.\n"
            "- PROCEDURE_INQUIRY: Technical questions about procedures, pain, or recovery.\n"
            "- AD_CONVERSION: Lead inquiring about a specific advertisement or call-to-action.\n"
            "- ORGANIC_INQUIRY: General interest in services, pricing, or catalog.\n"
            "- OFFER_CONVERSION: Responses to specific outbound marketing campaigns.\n"
            "- REENGAGEMENT_RECOVERY: Responses to re-engagement efforts after a period of inactivity.\n"
            "- GENERAL_INFO: Logistic questions (address, hours, payment methods).\n"
            "- IMAGE_ASSESSMENT: Mentioning or sending photos for visual analysis.\n"
            "- HUMAN_ESCALATION: Explicit request to talk to a human, manager, or owner."
        )
    )

    urgency_score = dspy.OutputField(desc="Score from 1 to 5 based on clinical risk. 5 is critical.")
    reasoning = dspy.OutputField(desc="Technical rationale for classification in English.")


# ============================================================================
# DSPY MODULE
# ============================================================================

class RouterModule(dspy.Module):
    """
    DSPy module that wraps the routing logic using Chain of Thought.
    """

    def __init__(self):
        super().__init__()
        self.classifier = dspy.ChainOfThought(RouterSignature)

    def forward(self, context_json: str, patient_message: str) -> dspy.Prediction:
        """
        Execute the routing classification.

        Args:
            context_json: JSON string with patient context
            patient_message: Latest WhatsApp message in PT-BR

        Returns:
            dspy.Prediction with intents, urgency_score, and reasoning
        """
        return self.classifier(
            context_json=context_json,
            patient_message=patient_message
        )


# ============================================================================
# LANGGRAPH NODES
# ============================================================================

import os

def router_node(state: AgentState) -> AgentState:
    import json
    router = RouterModule()
    
    # Language defined via Environment Variable (default to Portuguese)
    input_lang = os.getenv("INPUT_LANGUAGE", "Brazilian Portuguese")

    context_json = json.dumps(state["context"], ensure_ascii=False)

    prediction = router(
        context_json=context_json,
        input_language=input_lang, # Passando o idioma como parâmetro
        patient_message=state["latest_message"]
    )

    return {
        "intent_queue": prediction.intents,
        "urgency_score": prediction.urgency_score,
        "reasoning": prediction.rationale, # From ChainOfThought
    }


def placeholder_closer_agent(state: AgentState) -> AgentState:
    """
    Placeholder for the sales/closer agent.
    Handles SALES intents (pricing, offers, packages).

    TODO: Implement full closer agent logic
    """
    return {
        "final_response": "[CLOSER AGENT] Processing sales inquiry..."
    }


def placeholder_scheduler_agent(state: AgentState) -> AgentState:
    """
    Placeholder for the scheduling agent.
    Handles SCHEDULING intents (booking, rescheduling, cancellation).

    TODO: Implement full scheduler agent logic with Supabase integration
    """
    return {
        "final_response": "[SCHEDULER AGENT] Processing appointment request..."
    }


def placeholder_medical_agent(state: AgentState) -> AgentState:
    """
    Placeholder for the medical assessment agent.
    Handles MEDICAL_ASSESSMENT intents (health concerns, urgency).

    TODO: Implement full medical triage logic
    """
    return {
        "final_response": "[MEDICAL AGENT] Assessing medical concern..."
    }


def placeholder_faq_agent(state: AgentState) -> AgentState:
    """
    Placeholder for the FAQ/technical agent.
    Handles TECH_FAQ intents (procedure questions).

    TODO: Implement FAQ retrieval from knowledge base
    """
    return {
        "final_response": "[FAQ AGENT] Answering technical question..."
    }


# ============================================================================
# CONDITIONAL ROUTING
# ============================================================================

def should_continue(state: AgentState) -> Literal["closer_agent", "scheduler_agent",
                                                   "medical_agent", "faq_agent", "__end__"]:
    """
    Conditional edge function that determines the next agent based on intent_queue.

    Routing priority (highest to lowest):
    1. MEDICAL_ASSESSMENT - Always prioritized for patient safety
    2. SCHEDULING - Time-sensitive appointments
    3. SALES - Commercial inquiries
    4. TECH_FAQ - General questions
    5. END - No more intents to process

    Args:
        state: Current agent state with intent_queue

    Returns:
        String key for the next node or END
    """
    intent_queue = state.get("intent_queue", [])

    # If no intents remaining, end the flow
    if not intent_queue:
        return "__end__"

    # Check for medical urgency first (patient safety priority)
    if IntentType.MEDICAL_ASSESSMENT.value in intent_queue:
        return "medical_agent"

    # Then check for scheduling (time-sensitive)
    if IntentType.SCHEDULING.value in intent_queue:
        return "scheduler_agent"

    # Then sales inquiries
    if IntentType.SALES.value in intent_queue:
        return "closer_agent"

    # Technical/FAQ questions
    if IntentType.TECH_FAQ.value in intent_queue:
        return "faq_agent"

    # Default to end if only GENERAL_INFO or unknown
    return "__end__"


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def build_easyscale_graph() -> StateGraph:
    """
    Construct the complete LangGraph workflow for EasyScale.

    The graph structure:
    1. START -> router_node (classifies intent)
    2. router_node -> should_continue (conditional routing)
    3. should_continue branches to:
       - medical_agent (MEDICAL_ASSESSMENT priority)
       - scheduler_agent (SCHEDULING)
       - closer_agent (SALES)
       - faq_agent (TECH_FAQ)
       - END (no intents)

    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize the graph with our state schema
    workflow = StateGraph(AgentState)

    # Add the router node as entry point
    workflow.add_node("router", router_node)

    # Add placeholder agent nodes
    workflow.add_node("closer_agent", placeholder_closer_agent)
    workflow.add_node("scheduler_agent", placeholder_scheduler_agent)
    workflow.add_node("medical_agent", placeholder_medical_agent)
    workflow.add_node("faq_agent", placeholder_faq_agent)

    # Set the entry point
    workflow.set_entry_point("router")

    # Add conditional edges from router based on intent
    workflow.add_conditional_edges(
        "router",
        should_continue,
        {
            "closer_agent": "closer_agent",
            "scheduler_agent": "scheduler_agent",
            "medical_agent": "medical_agent",
            "faq_agent": "faq_agent",
            "__end__": END,
        }
    )

    # Each agent can loop back to router or end
    # (For now, they just end - expand this for multi-turn conversations)
    workflow.add_edge("closer_agent", END)
    workflow.add_edge("scheduler_agent", END)
    workflow.add_edge("medical_agent", END)
    workflow.add_edge("faq_agent", END)

    # Compile the graph
    return workflow.compile()


# ============================================================================
# CONFIGURATION & INITIALIZATION
# ============================================================================

def configure_dspy(
    provider: Literal["openai", "anthropic", "groq"] = "openai",
    model: str = "gpt-4o-mini",
    api_key: str = None,
    **kwargs
) -> None:
    """
    Configure DSPy with the specified language model.

    Args:
        provider: LLM provider to use
        model: Specific model identifier
        api_key: API key for the provider (if not in env)
        **kwargs: Additional configuration for the LM

    Example:
        >>> configure_dspy(provider="openai", model="gpt-4o-mini")
        >>> configure_dspy(provider="anthropic", model="claude-3-5-sonnet-20241022")
        >>> configure_dspy(provider="groq", model="llama-3.3-70b-versatile")
    """
    if provider == "openai":
        lm = dspy.LM(
            model=f"openai/{model}",
            api_key=api_key,
            **kwargs
        )
    elif provider == "anthropic":
        lm = dspy.LM(
            model=f"anthropic/{model}",
            api_key=api_key,
            **kwargs
        )
    elif provider == "groq":
        lm = dspy.LM(
            model=f"groq/{model}",
            api_key=api_key,
            **kwargs
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # Configure DSPy globally
    dspy.settings.configure(lm=lm)


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of the EasyScale router system.
    """
    import os

    # Configure DSPy (uses OPENAI_API_KEY from environment)
    configure_dspy(
        provider="openai",
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY")
    )

    # Build the graph
    graph = build_easyscale_graph()

    # Example patient context (from view_context_hydration)
    example_context = {
        "patient_id": "p_12345",
        "active_items": [
            {
                "service_name": "Limpeza de Pele Profunda",
                "price": 250.0,
                "status": "quoted"
            }
        ],
        "behavioral_profile": {
            "communication_style": "direct",
            "price_sensitivity": "medium",
            "decision_speed": "fast"
        },
        "conversation_history": [
            {"role": "patient", "text": "Oi, tenho interesse no tratamento"},
            {"role": "agent", "text": "Olá! Que ótimo! A limpeza de pele custa R$ 250."}
        ]
    }

    # Example 1: Sales inquiry
    print("\n=== Example 1: Sales Inquiry ===")
    result = graph.invoke({
        "context": example_context,
        "latest_message": "tá caro, tem como parcelar?",
        "intent_queue": [],
        "final_response": "",
        "urgency_score": 0,
        "reasoning": ""
    })
    print(f"Intents: {result['intent_queue']}")
    print(f"Urgency: {result['urgency_score']}")
    print(f"Reasoning: {result['reasoning']}")
    print(f"Response: {result['final_response']}")

    # Example 2: Scheduling
    print("\n=== Example 2: Scheduling ===")
    result = graph.invoke({
        "context": example_context,
        "latest_message": "quero marcar para semana que vem, tem vaga?",
        "intent_queue": [],
        "final_response": "",
        "urgency_score": 0,
        "reasoning": ""
    })
    print(f"Intents: {result['intent_queue']}")
    print(f"Urgency: {result['urgency_score']}")
    print(f"Response: {result['final_response']}")

    # Example 3: Medical urgency
    print("\n=== Example 3: Medical Urgency ===")
    result = graph.invoke({
        "context": example_context,
        "latest_message": "fiz o procedimento ontem e fiquei com alergia, está muito inchado",
        "intent_queue": [],
        "final_response": "",
        "urgency_score": 0,
        "reasoning": ""
    })
    print(f"Intents: {result['intent_queue']}")
    print(f"Urgency: {result['urgency_score']}")
    print(f"Reasoning: {result['reasoning']}")
    print(f"Response: {result['final_response']}")
