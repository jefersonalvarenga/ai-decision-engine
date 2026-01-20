@router.post("/run")
async def run_reengagement(payload: ReengageInput):
    # Executa o grafo
    final_state = app_graph.invoke(payload.dict())
    
    # Retorna para o n8n
    return {
        "chat_id": payload.chat_id,
        "message": final_state["final_response"],
        "meta": final_state["metadata"]
    }