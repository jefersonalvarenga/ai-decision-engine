"""
Router Agent State - Input/Output structures for intent classification

The router classifies patient messages into intentions that determine
which specialized agents should handle the conversation.
"""

from typing import TypedDict, List, Optional, Annotated, Dict, Any
from pydantic import BaseModel, Field
import operator


# ============================================================================
# LANGGRAPH STATE
# ============================================================================

class RouterState(TypedDict):
    """LangGraph state for Router flow"""
    # Inputs
    latest_incoming: str
    history: List[Dict[str, str]]  # [{role: "agent"|"human", content: "..."}]
    intake_status: str
    schedule_status: str
    reschedule_status: str
    cancel_status: str
    language: str

    # Outputs
    intentions: List[str]
    reasoning: str
    confidence: float


# ============================================================================
# API MODELS
# ============================================================================

class RouterInput(BaseModel):
    """Input from n8n to Router agent"""
    latest_incoming: str = Field(..., description="Última mensagem do paciente")
    history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Histórico da conversa [{role, content}]"
    )
    intake_status: str = Field(
        default="idle",
        description="Status do intake: idle, in_progress, completed"
    )
    schedule_status: str = Field(
        default="idle",
        description="Status do agendamento: idle, in_progress, completed"
    )
    reschedule_status: str = Field(
        default="idle",
        description="Status do reagendamento: idle, in_progress"
    )
    cancel_status: str = Field(
        default="idle",
        description="Status do cancelamento: idle, in_progress"
    )
    language: str = Field(
        default="pt-BR",
        description="Idioma do paciente"
    )


class RouterOutput(BaseModel):
    """Output from Router agent to n8n"""
    intentions: List[str] = Field(..., description="Lista de intenções identificadas")
    reasoning: str = Field(..., description="Explicação da decisão de roteamento")
    confidence: float = Field(..., description="Nível de confiança (0.0 a 1.0)")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")
