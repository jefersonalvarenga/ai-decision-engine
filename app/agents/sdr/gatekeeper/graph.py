"""
Gatekeeper Graph - LangGraph workflow for collecting manager contact

Simple linear graph: receive message → process → return action
The n8n workflow handles the actual messaging and state persistence.
"""

from langgraph.graph import StateGraph, END
from ..state import GatekeeperState
from .agent import GatekeeperAgent


# Initialize agent (singleton)
gatekeeper_agent = GatekeeperAgent()


def process_message(state: GatekeeperState) -> dict:
    """
    Main processing node - analyzes conversation and generates response.

    This is the only node in the graph. It:
    1. Receives current conversation state from n8n
    2. Processes with DSPy Chain of Thought
    3. Returns structured response for n8n to act on
    """
    print(f"--- GATEKEEPER: Processing message for {state['clinic_name']} ---")

    try:
        result = gatekeeper_agent.forward(
            clinic_name=state["clinic_name"],
            conversation_history=state.get("conversation_history", []),
            latest_message=state.get("latest_message"),
            current_hour=state.get("current_hour", 12),
            attempt_count=state.get("attempt_count", 0),
        )

        print(f"--- GATEKEEPER: Stage={result['conversation_stage']}, "
              f"Contact={result.get('extracted_manager_contact')} ---")

        return result

    except Exception as e:
        print(f"--- GATEKEEPER ERROR: {str(e)} ---")
        return {
            "reasoning": f"Erro no processamento: {str(e)}",
            "response_message": "Desculpe, tive um problema. Poderia repetir?",
            "conversation_stage": "handling_objection",
            "extracted_manager_contact": None,
            "extracted_manager_name": None,
            "should_send_message": True,
        }


# Build the graph
workflow = StateGraph(GatekeeperState)

# Single node - all processing happens here
workflow.add_node("process", process_message)

# Entry and exit
workflow.set_entry_point("process")
workflow.add_edge("process", END)

# Compile
gatekeeper_graph = workflow.compile()
