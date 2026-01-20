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
    context: Dict[str, Any]
    message: str

class RouterResponse(BaseModel):
    intents: List[str]
    urgency_score: int
    routed_to: str
    response: str
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
    Endpoint para mensagens em tempo real (WhatsApp).
    Decide se vai para agendamento, tirar dúvidas ou humano.
    """
    start_time = time.time()
    try:
        # Invoca o Grafo do Roteador
        result = router_graph.invoke({
            "context": request.context,
            "latest_message": request.message,
            "intent_queue": [],
            "final_response": "",
            "urgency_score": 0
        })

        return RouterResponse(
            intents=result.get("intent_queue", []),
            urgency_score=result.get("urgency_score", 1),
            routed_to=result.get("routed_to", "human"),
            response=result.get("final_response", ""),
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
            revision_count=result.get("revision_count", 0)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reengage Error: {str(e)}")

# ============================================================================
# SERVER RUNNER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)