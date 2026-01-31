"""
EasyScale Unified API
Suporta os fluxos de Roteamento (Router) e Re-engajamento (Re-engagement).
"""

import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importações dos seus módulos revisados
from app.core.config import get_settings, init_dspy
from app.agents.router.graph import app_graph as router_graph
from app.agents.reengage.graph import app_graph as reengage_graph
from app.agents.sdr import gatekeeper_graph, closer_graph
from app.agents.sdr.state import ConversationTurn
from app.core.security import SecurityMiddleware, AccessLogMiddleware

# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="EasyScale Clinic API",
    description="Sistema Multi-Agente para Clínicas de Estética",
    version="2.0.0"
)

# Middlewares
app.add_middleware(SecurityMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELS
# ============================================================================

class RouterRequest(BaseModel):
    """Request for Router agent - classifies patient intentions"""
    latest_incoming: str = Field(..., description="Última mensagem do paciente")
    history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Histórico da conversa [{role, content}]"
    )
    intake_status: str = Field(default="idle", description="Status do intake")
    schedule_status: str = Field(default="idle", description="Status do agendamento")
    reschedule_status: str = Field(default="idle", description="Status do reagendamento")
    cancel_status: str = Field(default="idle", description="Status do cancelamento")
    language: str = Field(default="pt-BR", description="Idioma do paciente")


class RouterResponse(BaseModel):
    """Response from Router agent"""
    intentions: List[str] = Field(..., description="Lista de intenções identificadas")
    reasoning: str = Field(..., description="Explicação da decisão")
    confidence: float = Field(..., description="Nível de confiança (0.0 a 1.0)")
    processing_time_ms: float

class ReengageRequest(BaseModel):
    lead_name: str
    ad_source: str
    psychographic_profile: str
    conversation_history: str

class ReengageResponse(BaseModel):
    generated_copy: str
    selected_strategy: str
    analyst_diagnosis: str
    revision_count: int


# SDR Models
class SDRConversationTurn(BaseModel):
    role: str = Field(..., pattern="^(agent|human)$")
    content: str


class GatekeeperRequest(BaseModel):
    """Request from n8n webhook for Gatekeeper agent"""
    clinic_name: str = Field(..., description="Nome da clínica")
    clinic_phone: str = Field(..., description="WhatsApp da clínica")
    conversation_history: List[SDRConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida (None se primeira mensagem)"
    )


class GatekeeperResponse(BaseModel):
    """Response to n8n with action to take"""
    response_message: str
    conversation_stage: str
    extracted_manager_contact: Optional[str] = None
    extracted_manager_name: Optional[str] = None
    should_send_message: bool
    reasoning: str
    processing_time_ms: float


class CloserRequest(BaseModel):
    """Request from n8n webhook for Closer agent"""
    manager_name: str = Field(..., description="Nome do gestor")
    manager_phone: str = Field(..., description="WhatsApp do gestor")
    clinic_name: str = Field(..., description="Nome da clínica")
    clinic_specialty: Optional[str] = Field(
        None,
        description="Especialidade: odonto, estética, etc"
    )
    conversation_history: List[SDRConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida"
    )
    available_slots: List[str] = Field(
        ...,
        description="Horários disponíveis no formato 'YYYY-MM-DD HH:MM'"
    )


class CloserResponse(BaseModel):
    """Response to n8n with action to take"""
    response_message: str
    conversation_stage: str
    meeting_datetime: Optional[str] = None
    meeting_confirmed: bool = False
    should_send_message: bool
    reasoning: str
    processing_time_ms: float

# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Inicializa o DSPy com as chaves do .env na subida do servidor."""
    print("🚀 EasyScale Clinic API starting...")
    try:
        init_dspy()
        print("✅ DSPy Motor initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing DSPy: {e}")

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/v1/health")
async def health():
    return {"status": "online", "timestamp": datetime.utcnow()}

@app.post("/v1/router", response_model=RouterResponse)
async def route_message(request: RouterRequest):
    """
    Endpoint para classificar intenções de mensagens de pacientes.

    Identifica quais agentes especializados devem ser ativados:
    - SERVICE_SCHEDULING: Agendamento
    - PROCEDURE_INQUIRY: Dúvidas sobre procedimentos
    - INTAKE: Coleta de informações médicas
    - HUMAN_ESCALATION: Escalar para humano
    - etc.
    """
    start_time = time.time()
    try:
        result = router_graph.invoke({
            "latest_incoming": request.latest_incoming,
            "history": request.history,
            "intake_status": request.intake_status,
            "schedule_status": request.schedule_status,
            "reschedule_status": request.reschedule_status,
            "cancel_status": request.cancel_status,
            "language": request.language,
        })

        return RouterResponse(
            intentions=result.get("intentions", ["UNCLASSIFIED"]),
            reasoning=result.get("reasoning", ""),
            confidence=result.get("confidence", 0.0),
            processing_time_ms=(time.time() - start_time) * 1000
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Router Error: {str(e)}")

@app.post("/v1/reengage", response_model=ReengageResponse)
async def reengage_lead(request: ReengageRequest):
    """
    Endpoint chamado pelo n8n para leads que pararam de responder.
    """
    try:
        # Invoca o Grafo de Re-engajamento (com loop de crítica)
        result = reengage_graph.invoke({
            "lead_name": request.lead_name,
            "ad_source": request.ad_source,
            "psychographic_profile": request.psychographic_profile,
            "conversation_history": request.conversation_history,
            "revision_count": 0,
            "is_approved": False
        })

        return ReengageResponse(
            generated_copy=result.get("generated_copy", ""),
            selected_strategy=result.get("selected_strategy", ""),
            analyst_diagnosis=result.get("analyst_diagnosis", ""),
            revision_count=result.get("revision_count", 0),
            critic_feedback=result.get("critic_feedback", "")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reengage Error: {str(e)}")


# ============================================================================
# SDR ENDPOINTS
# ============================================================================

@app.post("/v1/sdr/gatekeeper", response_model=GatekeeperResponse)
async def sdr_gatekeeper(request: GatekeeperRequest):
    """
    Endpoint para o fluxo Gatekeeper (coletar contato do gestor).

    Chamado pelo n8n quando:
    1. Inicia prospecção de uma nova clínica (conversation_history vazio)
    2. Recebe resposta da recepção (latest_message preenchido)

    Retorna ação para o n8n executar:
    - response_message: mensagem para enviar via Z-API
    - should_send_message: se deve enviar
    - extracted_manager_contact: telefone do gestor se conseguiu
    """
    start_time = time.time()
    current_hour = datetime.now().hour

    try:
        # Count agent messages in history
        attempt_count = len([
            t for t in request.conversation_history
            if t.role == "agent"
        ])

        result = gatekeeper_graph.invoke({
            "clinic_name": request.clinic_name,
            "conversation_history": [
                {"role": t.role, "content": t.content}
                for t in request.conversation_history
            ],
            "latest_message": request.latest_message,
            "current_hour": current_hour,
            "attempt_count": attempt_count,
        })

        return GatekeeperResponse(
            response_message=result.get("response_message", ""),
            conversation_stage=result.get("conversation_stage", "opening"),
            extracted_manager_contact=result.get("extracted_manager_contact"),
            extracted_manager_name=result.get("extracted_manager_name"),
            should_send_message=result.get("should_send_message", False),
            reasoning=result.get("reasoning", ""),
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gatekeeper Error: {str(e)}"
        )


@app.post("/v1/sdr/closer", response_model=CloserResponse)
async def sdr_closer(request: CloserRequest):
    """
    Endpoint para o fluxo Closer (agendar reunião com gestor).

    Chamado pelo n8n quando:
    1. Inicia contato com o gestor (conversation_history vazio)
    2. Recebe resposta do gestor (latest_message preenchido)

    Retorna ação para o n8n executar:
    - response_message: mensagem para enviar via Z-API
    - should_send_message: se deve enviar
    - meeting_datetime: ISO datetime se reunião foi confirmada
    - meeting_confirmed: true se deve criar evento no Google Calendar
    """
    start_time = time.time()
    current_hour = datetime.now().hour

    try:
        # Count agent messages in history
        attempt_count = len([
            t for t in request.conversation_history
            if t.role == "agent"
        ])

        result = closer_graph.invoke({
            "manager_name": request.manager_name,
            "manager_phone": request.manager_phone,
            "clinic_name": request.clinic_name,
            "clinic_specialty": request.clinic_specialty,
            "conversation_history": [
                {"role": t.role, "content": t.content}
                for t in request.conversation_history
            ],
            "latest_message": request.latest_message,
            "available_slots": request.available_slots,
            "current_hour": current_hour,
            "attempt_count": attempt_count,
        })

        return CloserResponse(
            response_message=result.get("response_message", ""),
            conversation_stage=result.get("conversation_stage", "greeting"),
            meeting_datetime=result.get("meeting_datetime"),
            meeting_confirmed=result.get("meeting_confirmed", False),
            should_send_message=result.get("should_send_message", False),
            reasoning=result.get("reasoning", ""),
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Closer Error: {str(e)}"
        )


# ============================================================================
# SERVER RUNNER
# ============================================================================

#if __name__ == "__main__":
#    import uvicorn
#    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# Substitua as últimas linhas por isso:
#ENV PYTHONPATH=.
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]