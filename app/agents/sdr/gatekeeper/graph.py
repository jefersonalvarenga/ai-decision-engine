"""
Gatekeeper Graph - LangGraph workflow for collecting manager contact

Flow:
  1. detect_persona  — classifica quem responde (roda a cada turno)
  2. route           — decide nó seguinte com base na persona
  3. process         — GatekeeperAgent (receptionist, manager, unknown, waiting, ai_assistant, call_center)
  4. process_menu_bot — MenuBotAgent (menu_bot)
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
    Classifica a persona a cada turno com base na latest_message + histórico.
    Roda sempre — sem cache, sem depender do detected_persona do Supabase.
    Pula apenas se ainda não há resposta da clínica (latest_message é None).
    """
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
# Node: process_menu_bot
# ---------------------------------------------------------------------------

def process_menu_bot(state: GatekeeperState) -> dict:
    """
    Tenta bypassar o bot de menu para chegar em um humano.
    O LLM analisa o histórico e decide a próxima ação.
    """
    history = state.get("conversation_history", [])
    print(f"--- GATEKEEPER: Persona=menu_bot — history_len={len(history)} ---")

    result = menu_bot_agent.forward(
        clinic_name=state["clinic_name"],
        conversation_history=history,
        latest_message=state.get("latest_message", ""),
    )

    print(f"--- MENU BOT: stage={result['conversation_stage']} msg={result['response_message']!r} ---")

    result["detected_persona"]   = state.get("detected_persona")
    result["persona_confidence"] = state.get("persona_confidence")
    result["_node_executed"]     = "process_menu_bot"
    return result


# ---------------------------------------------------------------------------
# Node: process
# ---------------------------------------------------------------------------

def process_message(state: GatekeeperState) -> dict:
    """
    Nó principal — processa com DSPy e gera a próxima resposta.
    Lida com todas as personas exceto menu_bot: receptionist, manager,
    unknown, waiting, ai_assistant, call_center.
    """
    persona = state.get("detected_persona") or "unknown"
    print(f"--- GATEKEEPER: Processing [{persona}] for {state['clinic_name']} ---")

    result = gatekeeper_agent.forward(
        clinic_name=state["clinic_name"],
        sdr_name=state.get("sdr_name", "Vera"),
        conversation_history=state.get("conversation_history", []),
        latest_message=state.get("latest_message"),
        current_hour=state.get("current_hour", 12),
        current_weekday=state.get("current_weekday", _dt.now().weekday()),
        detected_persona=persona,
    )

    print(
        f"--- GATEKEEPER: Stage={result['conversation_stage']}, "
        f"Contact={result.get('extracted_manager_contact')} ---"
    )

    result["detected_persona"]   = state.get("detected_persona")
    result["persona_confidence"] = state.get("persona_confidence")
    result["_node_executed"]     = "process"
    return result


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_by_persona(state: GatekeeperState) -> str:
    """Decide o próximo nó com base na persona detectada."""
    persona = state.get("detected_persona") or "unknown"
    if persona == "menu_bot":
        return "process_menu_bot"
    return "process"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

workflow = StateGraph(GatekeeperState)

workflow.add_node("detect_persona",   detect_persona)
workflow.add_node("process_menu_bot", process_menu_bot)
workflow.add_node("process",          process_message)

workflow.set_entry_point("detect_persona")

workflow.add_conditional_edges(
    "detect_persona",
    route_by_persona,
    {
        "process_menu_bot": "process_menu_bot",
        "process":          "process",
    },
)

workflow.add_edge("process_menu_bot", END)
workflow.add_edge("process",          END)

gatekeeper_graph = workflow.compile()
