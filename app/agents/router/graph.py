"""
Router Graph - LangGraph workflow for intent classification

Simple linear graph: receive message → classify intentions → return
"""

from langgraph.graph import StateGraph, END
from .state import RouterState
from .agent import RouterAgent


# Initialize agent (singleton)
router_agent = RouterAgent()


def classify_intentions(state: RouterState) -> dict:
    """
    Main processing node - classifies patient message into intentions.

    This is the only node in the graph. It:
    1. Receives message and context from n8n
    2. Processes with DSPy Chain of Thought
    3. Returns intentions for n8n to route to appropriate agents
    """
    print(f"--- ROUTER: Classifying message: {state['latest_incoming'][:50]}... ---")

    try:
        result = router_agent.forward(
            latest_incoming=state["latest_incoming"],
            history=state.get("history", []),
            intake_status=state.get("intake_status", "idle"),
            schedule_status=state.get("schedule_status", "idle"),
            reschedule_status=state.get("reschedule_status", "idle"),
            cancel_status=state.get("cancel_status", "idle"),
            language=state.get("language", "pt-BR"),
        )

        print(f"--- ROUTER: Intentions={result['intentions']}, "
              f"Confidence={result['confidence']:.2f} ---")

        return result

    except Exception as e:
        print(f"--- ROUTER ERROR: {str(e)} ---")
        return {
            "intentions": ["UNCLASSIFIED"],
            "reasoning": f"Erro no processamento: {str(e)}",
            "confidence": 0.0,
        }


# Build the graph
workflow = StateGraph(RouterState)

# Single node - all processing happens here
workflow.add_node("classify", classify_intentions)

# Entry and exit
workflow.set_entry_point("classify")
workflow.add_edge("classify", END)

# Compile
app_graph = workflow.compile()
