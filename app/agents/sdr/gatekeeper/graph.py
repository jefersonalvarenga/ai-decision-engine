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
from .menu_bot_agent import MenuBotAgent


# Singletons
gatekeeper_agent = GatekeeperAgent()
persona_detector  = PersonaDetector()
menu_bot_agent    = MenuBotAgent()


# ---------------------------------------------------------------------------
# Node: detect_persona
# ---------------------------------------------------------------------------

def detect_persona(state: GatekeeperState) -> dict:
    """
    Classifica a persona na primeira resposta da clínica.
    Pula se já detectada (exceto menu_bot — re-detecta para capturar humano que assumiu).
    Pula se ainda não há resposta da clínica (latest_message é None).
    """
    current_persona = state.get("detected_persona")
    latest = state.get("latest_message")

    # Sem resposta ainda — pula
    if not latest:
        return {}

    # Persona já conhecida e não é menu_bot — mantém
    if current_persona and current_persona != "menu_bot":
        return {}

    # menu_bot ou sem persona — (re-)detecta
    if current_persona == "menu_bot":
        print(f"--- PERSONA DETECTOR: Re-classificando — verificando se humano assumiu ---")
    else:
        print(f"--- PERSONA DETECTOR: Classificando resposta da {state['clinic_name']} ---")

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
        "conversation_stage": "call_center_blocked",
        "extracted_manager_contact": None,
        "extracted_manager_email": None,
        "extracted_manager_name": None,
        "should_send_message": True,
        "detected_persona": state.get("detected_persona"),
        "persona_confidence": state.get("persona_confidence"),
        "_node_executed": "exit_call_center",
    }


# ---------------------------------------------------------------------------
# Node: exit_ai_assistant
# ---------------------------------------------------------------------------

def exit_ai_assistant(state: GatekeeperState) -> dict:
    """
    Saída imediata para clínicas com IA conversacional.
    Não faz sentido tentar negociar com uma IA — ela nunca vai passar o contato do gestor.
    """
    print(f"--- GATEKEEPER: Persona=ai_assistant — saída imediata ---")
    return {
        "reasoning": "Assistente virtual de IA detectado. A IA não tem acesso ao gestor — encerrando.",
        "response_message": "Entendido, obrigado pela atenção!",
        "conversation_stage": "ai_blocked",
        "extracted_manager_contact": None,
        "extracted_manager_email": None,
        "extracted_manager_name": None,
        "should_send_message": True,
        "detected_persona": state.get("detected_persona"),
        "persona_confidence": state.get("persona_confidence"),
        "_node_executed": "exit_ai_assistant",
    }


# ---------------------------------------------------------------------------
# Node: process_menu_bot
# ---------------------------------------------------------------------------

def process_menu_bot(state: GatekeeperState) -> dict:
    """
    Tenta bypassar o bot de menu para chegar em um humano.
    Calcula bypass_attempts a partir do histórico (mensagens com stage handling_menu_bot).
    Após MAX_BYPASS_ATTEMPTS, encerra com failed.
    """
    history = state.get("conversation_history", [])
    bypass_attempts = sum(
        1 for t in history
        if t.get("role") == "agent" and t.get("stage") == "handling_menu_bot"
    )
    print(f"--- GATEKEEPER: Persona=menu_bot — bypass_attempts={bypass_attempts} history_len={len(history)} ---")
    print(f"--- GATEKEEPER: history stages={[(t.get('role'), t.get('stage')) for t in history]} ---")

    result = menu_bot_agent.forward(
        clinic_name=state["clinic_name"],
        conversation_history=history,
        latest_message=state.get("latest_message", ""),
        attempt_count=bypass_attempts,
    )

    print(f"--- MENU BOT: stage={result['conversation_stage']} msg={result['response_message']!r} ---")

    result["detected_persona"]   = state.get("detected_persona")
    result["persona_confidence"] = state.get("persona_confidence")
    result["attempt_count"]      = bypass_attempts + 1  # inclui a tentativa atual
    result["_node_executed"]     = "process_menu_bot"
    return result


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
        )

        print(
            f"--- GATEKEEPER: Stage={result['conversation_stage']}, "
            f"Contact={result.get('extracted_manager_contact')} ---"
        )

        # Propaga persona detectada para o output (n8n persiste)
        result["detected_persona"]   = state.get("detected_persona")
        result["persona_confidence"] = state.get("persona_confidence")
        result["_node_executed"]     = "process"
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
            "_node_executed": "process_error",
        }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_by_persona(state: GatekeeperState) -> str:
    """Decide o próximo nó com base na persona detectada."""
    persona = state.get("detected_persona") or "unknown"
    if persona == "call_center":
        return "exit_call_center"
    if persona == "ai_assistant":
        return "exit_ai_assistant"
    if persona == "menu_bot":
        return "process_menu_bot"
    return "process"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

workflow = StateGraph(GatekeeperState)

workflow.add_node("detect_persona",   detect_persona)
workflow.add_node("exit_call_center", exit_call_center)
workflow.add_node("exit_ai_assistant", exit_ai_assistant)
workflow.add_node("process_menu_bot", process_menu_bot)
workflow.add_node("process",          process_message)

workflow.set_entry_point("detect_persona")

workflow.add_conditional_edges(
    "detect_persona",
    route_by_persona,
    {
        "exit_call_center":  "exit_call_center",
        "exit_ai_assistant": "exit_ai_assistant",
        "process_menu_bot":  "process_menu_bot",
        "process":           "process",
    },
)

workflow.add_edge("exit_call_center",  END)
workflow.add_edge("exit_ai_assistant", END)
workflow.add_edge("process_menu_bot",  END)
workflow.add_edge("process",           END)

gatekeeper_graph = workflow.compile()
