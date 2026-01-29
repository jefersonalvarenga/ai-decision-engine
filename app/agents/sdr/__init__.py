"""
SDR Agents - Sales Development Representatives for clinic prospecting

Two main flows:
1. Gatekeeper: Talks to reception to get manager's contact
2. Closer: Talks to manager to schedule a meeting

Both agents are stateless - they receive context from n8n and return
structured actions for n8n to execute (send message, create calendar event, etc.)
"""

from .state import (
    ConversationTurn,
    GatekeeperInput,
    GatekeeperOutput,
    GatekeeperState,
    CloserInput,
    CloserOutput,
    CloserState,
)
from .gatekeeper import gatekeeper_graph, GatekeeperAgent
from .closer import closer_graph, CloserAgent

__all__ = [
    # State models
    "ConversationTurn",
    "GatekeeperInput",
    "GatekeeperOutput",
    "GatekeeperState",
    "CloserInput",
    "CloserOutput",
    "CloserState",
    # Graphs
    "gatekeeper_graph",
    "closer_graph",
    # Agents
    "GatekeeperAgent",
    "CloserAgent",
]
