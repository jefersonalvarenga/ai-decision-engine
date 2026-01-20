import dspy
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional
from .signatures import RouterSignature

# Definição do Estado do Roteador
class RouterState(TypedDict):
    context: dict
    latest_message: str
    intent_queue: List[str]
    urgency_score: int
    reasoning: str
    routed_to: str
    final_response: str

class RouterAgent(dspy.Module):
    def __init__(self):
        super().__init__()
        self.process = dspy.ChainOfThought(RouterSignature)

    def forward(self, state: RouterState):
        # Transforma o contexto em string para o DSPy processar melhor
        result = self.process(
            context=str(state['context']),
            latest_message=state['latest_message']
        )
        
        return {
            "intent_queue": result.intent_queue,
            "urgency_score": int(result.urgency_score),
            "reasoning": result.reasoning,
            "routed_to": result.routed_to,
            "final_response": result.final_response
        }

# Montagem do Grafo
def build_router_graph():
    router_agent = RouterAgent()
    
    workflow = StateGraph(RouterState)
    
    # Adicionamos o nó principal
    workflow.add_node("router_node", router_agent.forward)
    
    # Fluxo linear simples: entra, processa e termina
    workflow.set_entry_point("router_node")
    workflow.add_edge("router_node", END)
    
    return workflow.compile()

# Instância que o main.py importa
app_graph = build_router_graph()