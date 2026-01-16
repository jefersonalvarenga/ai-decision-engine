from typing import TypedDict, List, Annotated, Optional
import operator

class AgentState(TypedDict):
    lead_id: str
    lead_name: str
    target_language: str
    psychographic_profile: dict
    conversation_history: List[dict]
    ad_source: str
    analyst_diagnosis: str
    selected_strategy: str
    generated_copy: str
    critic_feedback: str
    copy_attempts: Annotated[int, operator.add]
    approval_status: bool