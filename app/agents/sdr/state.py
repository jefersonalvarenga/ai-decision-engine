"""
SDR Agent States - Input/Output structures for n8n integration

The n8n workflow is responsible for:
- Fetching leads from Google Sheets
- Persisting conversation history
- Sending messages via Z-API
- Creating events in Google Calendar

The agents are stateless processors that receive context and return structured actions.
"""

from typing import TypedDict, List, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# SHARED STRUCTURES
# ============================================================

class ConversationTurn(BaseModel):
    """Single turn in a conversation"""
    role: Literal["agent", "human"]
    content: str


# ============================================================
# GATEKEEPER FLOW - Collect manager contact from reception
# ============================================================

class GatekeeperInput(BaseModel):
    """Input from n8n to Gatekeeper agent"""
    clinic_name: str = Field(..., description="Nome da clínica")
    clinic_phone: str = Field(..., description="WhatsApp da clínica")
    conversation_history: List[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa (vazio se primeira mensagem)"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida da recepção (None se primeira mensagem)"
    )


class GatekeeperOutput(BaseModel):
    """Output from Gatekeeper agent to n8n"""
    response_message: str = Field(..., description="Mensagem para enviar")
    conversation_stage: Literal[
        "opening",            # Primeira msg: "é da clínica X?"
        "requesting",         # Pedindo contato do gestor
        "handling_objection", # Respondendo "do que se trata?"
        "success",            # Conseguiu o contato
        "failed"              # Desistiu (muitas tentativas ou negativa definitiva)
    ] = Field(..., description="Estágio atual da conversa")
    extracted_manager_contact: Optional[str] = Field(
        None,
        description="Telefone do gestor se foi informado"
    )
    extracted_manager_name: Optional[str] = Field(
        None,
        description="Nome do gestor se foi informado"
    )
    should_send_message: bool = Field(
        ...,
        description="Se deve enviar a mensagem (false quando acabou)"
    )
    reasoning: str = Field(..., description="Explicação da decisão do agente")


# ============================================================
# CLOSER FLOW - Schedule meeting with manager
# ============================================================

class CloserInput(BaseModel):
    """Input from n8n to Closer agent"""
    manager_name: str = Field(..., description="Nome do gestor (ex: Dr. Marcos)")
    manager_phone: str = Field(..., description="WhatsApp do gestor")
    clinic_name: str = Field(..., description="Nome da clínica")
    clinic_specialty: Optional[str] = Field(
        None,
        description="Especialidade: odonto, estética, etc"
    )
    conversation_history: List[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida do gestor"
    )
    available_slots: List[str] = Field(
        ...,
        description="Horários disponíveis no formato 'YYYY-MM-DD HH:MM'"
    )


class CloserOutput(BaseModel):
    """Output from Closer agent to n8n"""
    response_message: str = Field(
        ...,
        description="Mensagem(ns) para enviar, separadas por ||| se múltiplas"
    )
    conversation_stage: Literal[
        "greeting",        # Apresentação inicial
        "pitching",        # Explicando proposta
        "proposing_time",  # Propondo horário
        "confirming",      # Confirmando horário escolhido
        "scheduled",       # Reunião agendada!
        "lost"             # Lead perdido
    ] = Field(..., description="Estágio atual da conversa")
    meeting_datetime: Optional[str] = Field(
        None,
        description="ISO datetime se confirmou reunião (ex: 2024-01-30T15:30:00)"
    )
    meeting_confirmed: bool = Field(
        False,
        description="True se a reunião foi confirmada"
    )
    should_send_message: bool = Field(
        ...,
        description="Se deve enviar a mensagem"
    )
    reasoning: str = Field(..., description="Explicação da decisão do agente")


# ============================================================
# LANGGRAPH STATE DEFINITIONS
# ============================================================

class GatekeeperState(TypedDict):
    """LangGraph state for Gatekeeper flow"""
    # Inputs
    clinic_name: str
    conversation_history: list
    latest_message: Optional[str]
    current_hour: int
    attempt_count: int
    # Outputs
    response_message: Optional[str]
    conversation_stage: str
    extracted_manager_contact: Optional[str]
    extracted_manager_name: Optional[str]
    should_send_message: bool
    reasoning: str


class CloserState(TypedDict):
    """LangGraph state for Closer flow"""
    # Inputs
    manager_name: str
    manager_phone: str
    clinic_name: str
    clinic_specialty: Optional[str]
    conversation_history: list
    latest_message: Optional[str]
    available_slots: list
    current_hour: int
    attempt_count: int
    # Outputs
    response_message: Optional[str]
    conversation_stage: str
    meeting_datetime: Optional[str]
    meeting_confirmed: bool
    should_send_message: bool
    reasoning: str
