from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import AnalystAgent

# Instanciar o agente
analyst_agent = AnalystAgent()

def call_analyst(state: AgentState):
    # Log para debug no console do Easypanel
    print(f"--- STARTING ANALYSIS FOR: {state.get('lead_name')} ---")
    
    try:
        # Chama o DSPy
        diagnosis = analyst_agent.forward(state)
        
        # Forçamos ser string para evitar erros de serialização JSON
        return {"analyst_diagnosis": str(diagnosis)}
    except Exception as e:
        print(f"--- ERROR IN ANALYST NODE: {e} ---")
        return {"analyst_diagnosis": f"Error during analysis: {str(e)}"}

workflow = StateGraph(AgentState)
workflow.add_node("analyst", call_analyst)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", END)

app_graph = workflow.compile()