from typing import TypedDict, Optional, Annotated
import operator

class ReengageState(TypedDict):
    # Inputs do Supabase
    lead_name: str
    ad_source: str
    psychographic_profile: str
    conversation_history: str
    
    # Outputs dos Agentes
    analyst_diagnosis: Optional[str]
    selected_strategy: Optional[str]
    generated_copy: Optional[str]
    critic_feedback: Optional[str]
    
    # Controle de Fluxo
    is_approved: bool
    revision_count: Annotated[int, operator.add]