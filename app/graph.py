from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import AnalystAgent, StrategistAgent, CopywriterAgent # Atualize o import

# Instanciar os agentes
analyst_agent = AnalystAgent()
strategist_agent = StrategistAgent()
copywriter_agent = CopywriterAgent()

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

def call_copywriter(state: AgentState):
    print("--- GENERATING FINAL COPY ---")
    copy = copywriter_agent.forward(
        state["selected_strategy"],
        state["analyst_diagnosis"],
        state["target_language"]
    )
    return {"generated_copy": copy}

# Configuração do Grafo
workflow = StateGraph(AgentState)

workflow.add_node("analyst", call_analyst)
workflow.add_node("strategist", call_strategist)
workflow.add_node("copywriter", call_copywriter) # Novo nó

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "strategist")
workflow.add_edge("strategist", "copywriter") # Fluxo linear
workflow.add_edge("copywriter", END)

app_graph = workflow.compile()