from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import AnalystAgent, StrategistAgent, CopywriterAgent, CriticAgent

# Instanciar os agentes
analyst_agent = AnalystAgent()
strategist_agent = StrategistAgent()
copywriter_agent = CopywriterAgent()
critic_agent = CriticAgent()

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

def call_critic(state: AgentState):
    print("--- CRITIQUING THE MESSAGE ---")
    feedback, approved = critic_agent.forward(
        state["generated_copy"], 
        state["analyst_diagnosis"]
    )
    
    # Se reprovado, incrementamos o contador de tentativas
    # O state["copy_attempts"] será somado automaticamente via operator.add
    return {
        "critic_feedback": feedback,
        "approval_status": approved,
        "copy_attempts": 1 
    }

# Função lógica para decidir o próximo passo
def decide_to_retry(state: AgentState):
    if state["approval_status"] is True or state["copy_attempts"] >= 3:
        return END
    return "copywriter" # Se reprovado e tiver tentativas, volta para escrever de novo

workflow = StateGraph(AgentState)

workflow.add_node("analyst", call_analyst)
workflow.add_node("strategist", call_strategist)
workflow.add_node("copywriter", call_copywriter)
workflow.add_node("critic", call_critic)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "strategist")
workflow.add_edge("strategist", "copywriter")
workflow.add_edge("copywriter", "critic") # Após o copy, vai para o crítico

# Aresta Condicional: Se o crítico reprovar, volta para o copywriter
workflow.add_conditional_edges(
    "critic",
    decide_to_retry
)

app_graph = workflow.compile()