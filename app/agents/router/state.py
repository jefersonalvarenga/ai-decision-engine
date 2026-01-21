# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    latest_incoming: str
    history: List[str]
    intake_status: str       # 'in_progress' ou 'completed'
    schedule_status: str     # 'in_progress' ou 'idle'
    reschedule_status: str   # 'in_progress' ou 'idle'
    cancel_status: str       # 'in_progress' ou 'idle'
    language: str     # 'PT-BR' ou EN-US
    
    # Resultados do Router
    intentions: Annotated[List[str], operator.add]
    reasoning: str
    confidence: float