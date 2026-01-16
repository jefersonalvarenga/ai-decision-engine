import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Importação única e limpa
# O ponto (.) antes do graph indica que ele está na mesma pasta 'app'
from .graph import app_graph
from .state import AgentState

load_dotenv()

app = FastAPI(title="Engagement Engine Elite")

class n8nPayload(BaseModel):
    lead_id: str
    name: str
    profile: dict
    ad_source: str
    language: str = "pt-BR"

@app.get("/health")
def health():
    return {"status": "operational", "engine": "FastAPI + LangGraph"}

@app.post("/v1/reengage")
async def start_reengagement(payload: n8nPayload):
    # 1. Preparar o estado inicial rigorosamente igual ao AgentState
    initial_state: AgentState = {
        "lead_id": payload.lead_id,
        "lead_name": payload.name,
        "target_language": payload.language,
        "psychographic_profile": payload.profile,
        "conversation_history": [], 
        "ad_source": payload.ad_source,
        "analyst_diagnosis": "",
        "selected_strategy": "",
        "generated_copy": "",
        "critic_feedback": "",
        "copy_attempts": 0,
        "approval_status": False
    }

    try:
        # 2. Executar o Grafo
        final_state = await app_graph.ainvoke(initial_state)

        # 3. Retornar o resultado
        return {
            "lead_id": final_state["lead_id"],
            "diagnosis": final_state["analyst_diagnosis"],
            "status": "analyzed"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}