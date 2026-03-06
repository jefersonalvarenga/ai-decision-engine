"""
Gatekeeper Graph - LangGraph workflow for collecting manager contact

Flow:
  1. detect_persona  — classifica quem responde (roda só uma vez por conversa)
  2. route           — decide nó seguinte com base na persona
  3. process_message — agente principal (Persona 1 e 5)
  4. exit_call_center — saída imediata sem LLM (Persona 4)

O n8n persiste detected_persona entre turnos para evitar re-classificação.
"""

from datetime import datetime as _dt

from langgraph.graph import StateGraph, END
from ..state import GatekeeperState
from .agent import GatekeeperAgent
from .persona_detector import PersonaDetector


# Singletons
gatekeeper_agent = GatekeeperAgent()
persona_detector  = PersonaDetector()


# ---------------------------------------------------------------------------
# Node: detect_persona
# ---------------------------------------------------------------------------

def detect_persona(state: GatekeeperState) -> dict:
    """
    Classifica a persona na primeira resposta da clínica.
    Pula se já detectada (detected_persona presente no state).
    Pula se ainda não há resposta da clínica (latest_message é None).
    """
    # Já detectada em turno anterior — mantém
    if state.get("detected_persona"):
        return {}

    # Primeira mensagem (agente ainda não recebeu resposta) — pula
    latest = state.get("latest_message")
    if not latest:
        return {}

    print(f"--- PERSONA DETECTOR: Classificando resposta da {state['clinic_name']} ---")

    result = persona_detector.forward(
        clinic_name=state["clinic_name"],
        conversation_history=state.get("conversation_history", []),
        latest_message=latest,
    )

    print(
        f"--- PERSONA DETECTOR: persona={result['persona']} "
        f"confidence={result['confidence']} | {result['key_signal']!r} ---"
    )

    return {
        "detected_persona": result["persona"],
        "persona_confidence": result["confidence"],
    }


# ---------------------------------------------------------------------------
# Node: exit_call_center
# ---------------------------------------------------------------------------

def exit_call_center(state: GatekeeperState) -> dict:
    """
    Saída imediata para centrais de atendimento terceirizadas.
    Não chama LLM — a atendente não tem acesso ao gestor.
    """
    print(f"--- GATEKEEPER: Persona=call_center — saída imediata ---")
    return {
        "reasoning": "Central de atendimento detectada. Sem acesso ao gestor — encerrando.",
        "response_message": "Entendido, obrigado pela atenção!",
        "conversation_stage": "failed",
        "extracted_manager_contact": None,
        "extracted_manager_email": None,
        "extracted_manager_name": None,
        "should_send_message": True,
        "detected_persona": state.get("detected_persona"),
        "persona_confidence": state.get("persona_confidence"),
    }


# ---------------------------------------------------------------------------
# Node: process_message
# ---------------------------------------------------------------------------

def process_message(state: GatekeeperState) -> dict:
    """
    Nó principal — processa com DSPy e gera a próxima resposta.
    Recebe detected_persona como contexto (sem alterar a signature atual).
    """
    persona = state.get("detected_persona") or "unknown"
    print(f"--- GATEKEEPER: Processing [{persona}] for {state['clinic_name']} ---")

    try:
        result = gatekeeper_agent.forward(
            clinic_name=state["clinic_name"],
            sdr_name=state.get("sdr_name", "Vera"),
            conversation_history=state.get("conversation_history", []),
            latest_message=state.get("latest_message"),
            current_hour=state.get("current_hour", 12),
            current_weekday=state.get("current_weekday", _dt.now().weekday()),
            attempt_count=state.get("attempt_count", 0),
        )

        print(
            f"--- GATEKEEPER: Stage={result['conversation_stage']}, "
            f"Contact={result.get('extracted_manager_contact')} ---"
        )

        # Propaga persona detectada para o output (n8n persiste)
        result["detected_persona"]   = state.get("detected_persona")
        result["persona_confidence"] = state.get("persona_confidence")
        return result

    except Exception as e:
        print(f"--- GATEKEEPER ERROR: {str(e)} ---")
        return {
            "reasoning": f"Erro no processamento: {str(e)}",
            "response_message": "Desculpe, tive um problema. Poderia repetir?",
            "conversation_stage": "handling_objection",
            "extracted_manager_contact": None,
            "extracted_manager_name": None,
            "should_send_message": True,
            "detected_persona": state.get("detected_persona"),
            "persona_confidence": state.get("persona_confidence"),
        }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_by_persona(state: GatekeeperState) -> str:
    """Decide o próximo nó com base na persona detectada."""
    persona = state.get("detected_persona") or "unknown"
    if persona == "call_center":
        return "exit_call_center"
    return "process"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

workflow = StateGraph(GatekeeperState)

workflow.add_node("detect_persona",   detect_persona)
workflow.add_node("exit_call_center", exit_call_center)
workflow.add_node("process",          process_message)

workflow.set_entry_point("detect_persona")

workflow.add_conditional_edges(
    "detect_persona",
    route_by_persona,
    {
        "exit_call_center": "exit_call_center",
        "process":          "process",
    },
)

workflow.add_edge("exit_call_center", END)
workflow.add_edge("process",          END)

gatekeeper_graph = workflow.compile()
