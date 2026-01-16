from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import AnalystAgent, StrategistAgent # Atualize o import

# Instanciar os agentes
analyst_agent = AnalystAgent()
strategist_agent = StrategistAgent()

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

def call_strategist(state: AgentState):
    print("--- SELECTING STRATEGY ---")
    diagnosis = state["analyst_diagnosis"]
    
    # Chama o Strategist
    strategy, rationale = strategist_agent.forward(diagnosis)
    
    print(f"--- STRATEGY CHOSEN: {strategy} ---")
    return {
        "selected_strategy": f"{strategy}: {rationale}"
    }

# --- Atualização do Workflow ---
workflow = StateGraph(AgentState)
workflow.add_node("analyst", call_analyst)
workflow.add_node("strategist", call_strategist) # Novo nó

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "strategist") # Conecta Analista ao Estrategista
workflow.add_edge("strategist", END)      # Termina após Estrategista

app_graph = workflow.compile()