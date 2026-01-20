"""
EasyScale FastAPI Integration

This module provides the REST API endpoints for the EasyScale router system.
It receives WhatsApp messages, processes them through the router agent,
and returns the appropriate response.
"""

from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from router_agent import build_easyscale_graph, configure_dspy
from config import get_settings, EasyScaleSettings


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="EasyScale Router API",
    description="Intelligent routing system for aesthetic clinic customer service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message from webhook."""

    patient_id: str = Field(description="Unique patient identifier")
    message: str = Field(description="Message text in PT-BR")
    phone: str = Field(description="Patient's phone number")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata (media, location, etc.)"
    )


class RouterRequest(BaseModel):
    """Request model for router endpoint."""

    context: Dict[str, Any] = Field(
        description="Patient context from view_context_hydration"
    )
    message: str = Field(
        description="Latest WhatsApp message in PT-BR"
    )


class RouterResponse(BaseModel):
    """Response model from router."""

    intents: list[str] = Field(description="Detected intent types")
    urgency_score: int = Field(
        ge=1, le=5,
        description="Urgency score (1=low, 5=critical)"
    )
    reasoning: str = Field(description="Internal reasoning (English)")
    routed_to: str = Field(description="Agent that will handle this")
    response: str = Field(description="Generated response for patient")
    processing_time_ms: float = Field(description="Processing time in milliseconds")


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    dspy_configured: bool
    timestamp: datetime


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

def get_graph():
    """
    Dependency to get the compiled LangGraph.
    Cached as a singleton for performance.
    """
    if not hasattr(get_graph, "_graph"):
        settings = get_settings()

        # Configure DSPy on first call
        configure_dspy(
            provider=settings.dspy_provider,
            model=settings.dspy_model,
            api_key=settings.get_api_key(),
        )

        # Build and cache the graph
        get_graph._graph = build_easyscale_graph()

    return get_graph._graph


async def verify_api_key(x_api_key: str = Header(...)) -> bool:
    """
    Verify API key from header.

    TODO: Implement proper API key validation
    """
    # Placeholder - implement actual verification
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required"
        )
    return True


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_model=HealthCheckResponse)
async def root():
    """Root endpoint - health check."""
    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        dspy_configured=hasattr(get_graph, "_graph"),
        timestamp=datetime.utcnow()
    )


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint for monitoring."""
    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        dspy_configured=hasattr(get_graph, "_graph"),
        timestamp=datetime.utcnow()
    )


@app.post("/api/v1/router", response_model=RouterResponse)
async def route_message(
    request: RouterRequest,
    graph=Depends(get_graph),
    # _authenticated: bool = Depends(verify_api_key)  # Uncomment for auth
) -> RouterResponse:
    """
    Main routing endpoint.

    Receives a patient message and context, classifies intent,
    and routes to the appropriate agent.

    Example request:
    ```json
    {
        "context": {
            "patient_id": "p_12345",
            "active_items": [{"service_name": "Botox", "price": 800}],
            "behavioral_profile": {"communication_style": "direct"}
        },
        "message": "quanto custa e dá pra parcelar?"
    }
    ```
    """
    import time

    start_time = time.time()

    try:
        # Execute the graph
        result = graph.invoke({
            "context": request.context,
            "latest_message": request.message,
            "intent_queue": [],
            "final_response": "",
            "urgency_score": 0,
            "reasoning": ""
        })

        processing_time = (time.time() - start_time) * 1000

        # Determine which agent was routed to
        from router_agent import should_continue
        routed_to = should_continue(result)
        if routed_to == "__end__":
            routed_to = "none"

        return RouterResponse(
            intents=result["intent_queue"],
            urgency_score=result["urgency_score"],
            reasoning=result["reasoning"],
            routed_to=routed_to,
            response=result["final_response"],
            processing_time_ms=processing_time
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Routing failed: {str(e)}"
        )


@app.post("/api/v1/whatsapp/webhook")
async def whatsapp_webhook(
    message: WhatsAppMessage,
    settings: EasyScaleSettings = Depends(get_settings),
    graph=Depends(get_graph)
):
    """
    WhatsApp webhook endpoint.

    Receives messages from WhatsApp Business API, fetches patient context
    from Supabase, routes through the agent system, and returns response.

    TODO: Implement full WhatsApp Business API integration
    """
    try:
        # 1. Fetch patient context from Supabase
        from supabase import create_client
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key
        )

        # Query the view_context_hydration
        context_result = supabase.from_("view_context_hydration")\
            .select("*")\
            .eq("patient_id", message.patient_id)\
            .single()\
            .execute()

        if not context_result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {message.patient_id} not found"
            )

        patient_context = context_result.data

        # 2. Route through the agent system
        result = graph.invoke({
            "context": patient_context,
            "latest_message": message.message,
            "intent_queue": [],
            "final_response": "",
            "urgency_score": 0,
            "reasoning": ""
        })

        # 3. Log the interaction to Supabase
        supabase.from_("conversation_logs").insert({
            "patient_id": message.patient_id,
            "message_in": message.message,
            "message_out": result["final_response"],
            "intents": result["intent_queue"],
            "urgency_score": result["urgency_score"],
            "reasoning": result["reasoning"],
            "timestamp": message.timestamp.isoformat()
        }).execute()

        # 4. Return response for WhatsApp
        return {
            "response": result["final_response"],
            "urgency": result["urgency_score"]
        }

    except Exception as e:
        # Log error but don't expose to WhatsApp
        print(f"Error processing webhook: {e}")
        return {
            "response": "Desculpe, tive um problema ao processar sua mensagem. "
                       "Nossa equipe já foi notificada e retornaremos em breve."
        }


@app.post("/api/v1/test/classify")
async def test_classification(
    message: str,
    graph=Depends(get_graph)
):
    """
    Test endpoint for quick intent classification.

    Useful for debugging and testing different PT-BR phrases.
    """
    # Minimal context for testing
    test_context = {
        "patient_id": "test",
        "active_items": [],
        "behavioral_profile": {}
    }

    result = graph.invoke({
        "context": test_context,
        "latest_message": message,
        "intent_queue": [],
        "final_response": "",
        "urgency_score": 0,
        "reasoning": ""
    })

    return {
        "message": message,
        "intents": result["intent_queue"],
        "urgency": result["urgency_score"],
        "reasoning": result["reasoning"]
    }


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    print("🚀 EasyScale Router API starting...")

    settings = get_settings()
    print(f"   Provider: {settings.dspy_provider}")
    print(f"   Model: {settings.dspy_model}")

    # Pre-compile the graph
    get_graph()
    print("   ✓ LangGraph compiled")

    print("✅ Ready to receive requests!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("👋 EasyScale Router API shutting down...")


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Disable in production
        log_level="info"
    )
