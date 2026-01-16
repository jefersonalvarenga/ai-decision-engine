from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import AnalystAgent

# 1. Instanciar os agentes
analyst_agent = AnalystAgent()

# 2. Definir as funções dos nós (Nodes)
# Cada nó recebe o State atual e retorna apenas o que ele alterou
def call_analyst(state: AgentState):
    print(f"--- ANALYZING LEAD: {state['lead_name']} ---")
    
    # Chama o DSPy para o diagnóstico
    diagnosis = analyst_agent.forward(state)
    
    # Retorna a atualização do estado
    return {
        "analyst_diagnosis": diagnosis
    }

# 3. Construir o Grafo
workflow = StateGraph(AgentState)

# Adicionar os nós na esteira
workflow.add_node("analyst", call_analyst)

# 4. Definir as Arestas (Edges) - O fluxo de execução
workflow.set_entry_point("analyst") # Começa pelo analista
workflow.add_edge("analyst", END)    # Por enquanto, termina após a análise

# 5. Compilar o Grafo
# O checkpointer (opcional no futuro) permitiria pausar e retomar a conversa
app_graph = workflow.compile()