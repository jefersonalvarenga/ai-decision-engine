import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

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

@app.post("/v1/reengage")
async def start_reengagement(payload: n8nPayload):
    # Criando o estado inicial rigoroso
    initial_state: AgentState = {
        "lead_id": payload.lead_id,
        "lead_name": payload.name,
        "target_language": payload.language,
        "psychographic_profile": payload.profile,
        "conversation_history": [], # O nó de busca no Supabase preencherá isso
        "ad_source": payload.ad_source,
        "analyst_diagnosis": "",
        "selected_strategy": "",
        "generated_copy": "",
        "critic_feedback": "",
        "copy_attempts": 0,
        "approval_status": False
    }
    
    # Aqui entrará: await graph.ainvoke(initial_state)
    
    return {
        "lead_id": payload.lead_id,
        "status": "received",
        "message": "Brain ready. Logic injected."
    }