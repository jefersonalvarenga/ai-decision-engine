import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from .graph import app_graph

load_dotenv()

app = FastAPI(title="Engagement Engine Elite")

class n8nPayload(BaseModel):
    lead_id: str
    name: str
    profile: dict
    ad_source: str
    language: str = "pt-BR" # Default

@app.get("/health")
def health():
    return {"status": "operational", "engine": "FastAPI + LangGraph"}

# ... seus imports anteriores ...
from .graph import app_graph

@app.post("/v1/reengage")
async def start_reengagement(payload: n8nPayload):
    # 1. Preparar o estado inicial
    initial_state = {
        "lead_id": payload.lead_id,
        "lead_name": payload.name,
        "target_language": payload.language,
        "psychographic_profile": payload.profile,
        "conversation_history": [], # Aqui você pode buscar no Supabase depois
        "ad_source": payload.ad_source,
        "analyst_diagnosis": "",
        "selected_strategy": "",
        "generated_copy": "",
        "critic_feedback": "",
        "copy_attempts": 0,
        "approval_status": False
    }

    # 2. Executar o Grafo (A mágica acontece aqui)
    # Usamos o 'ainvoke' para ser assíncrono (FastAPI adora isso)
    final_state = await app_graph.ainvoke(initial_state)

    # 3. Retornar o resultado processado
    return {
        "lead_id": final_state["lead_id"],
        "diagnosis": final_state["analyst_diagnosis"],
        "status": "analyzed"
    }