"""
Closer Graph - LangGraph workflow for scheduling meetings with managers

Simple linear graph: receive message → process → return action
The n8n workflow handles the actual messaging, calendar integration, and state persistence.
"""

from langgraph.graph import StateGraph, END
from ..state import CloserState
from .agent import CloserAgent


# Initialize agent (singleton)
closer_agent = CloserAgent()


def process_message(state: CloserState) -> dict:
    """
    Main processing node - analyzes conversation and generates response.

    This is the only node in the graph. It:
    1. Receives current conversation state from n8n
    2. Processes with DSPy Chain of Thought
    3. Returns structured response for n8n to act on (send message, create calendar event)
    """
    print(f"--- CLOSER: Processing message for {state['manager_name']} ({state['clinic_name']}) ---")

    try:
        result = closer_agent.forward(
            manager_name=state["manager_name"],
            clinic_name=state["clinic_name"],
            clinic_specialty=state.get("clinic_specialty"),
            conversation_history=state.get("conversation_history", []),
            latest_message=state.get("latest_message"),
            available_slots=state.get("available_slots", []),
            current_hour=state.get("current_hour", 12),
            attempt_count=state.get("attempt_count", 0),
        )

        print(f"--- CLOSER: Stage={result['conversation_stage']}, "
              f"Meeting={result.get('meeting_datetime')} ---")

        return result

    except Exception as e:
        print(f"--- CLOSER ERROR: {str(e)} ---")
        return {
            "reasoning": f"Erro no processamento: {str(e)}",
            "response_message": "Desculpe, tive um problema técnico. Podemos continuar?",
            "conversation_stage": "pitching",
            "meeting_datetime": None,
            "meeting_confirmed": False,
            "should_send_message": True,
        }


# Build the graph
workflow = StateGraph(CloserState)

# Single node - all processing happens here
workflow.add_node("process", process_message)

# Entry and exit
workflow.set_entry_point("process")
workflow.add_edge("process", END)

# Compile
closer_graph = workflow.compile()
