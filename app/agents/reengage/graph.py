from langgraph.graph import StateGraph, END
from .state import ReengageState
from .analyst import AnalystAgent
from .strategist import StrategistAgent
from .copywriter import CopywriterAgent
from .critic import CriticAgent

# Instantiating agents
# Each agent's .forward() will be used as a node logic
analyst_agent = AnalystAgent()
strategist_agent = StrategistAgent()
copywriter_agent = CopywriterAgent()
critic_agent = CriticAgent()

# --- NODE WRAPPERS ---

def call_analyst(state: ReengageState):
    print(f"--- STARTING ANALYSIS FOR: {state.get('lead_name')} ---")
    try:
        # Our refined AnalystAgent expects 'state' and returns a dict
        return analyst_agent.forward(state)
    except Exception as e:
        print(f"--- ERROR IN ANALYST NODE: {e} ---")
        return {"analyst_diagnosis": f"Error during analysis: {str(e)}"}

def call_strategist(state: ReengageState):
    print("--- SELECTING STRATEGY ---")
    # Our refined StrategistAgent expects 'state' and returns a dict
    return strategist_agent.forward(state)

def call_copywriter(state: ReengageState):
    print("--- GENERATING FINAL COPY ---")
    # Our refined CopywriterAgent expects 'state' and returns a dict
    return copywriter_agent.forward(state)

def call_critic(state: ReengageState):
    print("--- CRITIQUING THE MESSAGE ---")
    # Our refined CriticAgent expects 'state' and returns a dict
    # It returns 'is_approved', 'critic_feedback' and increment for 'revision_count'
    return critic_agent.forward(state)

# --- CONDITIONAL LOGIC ---

def decide_to_retry(state: ReengageState):
    """
    Decides whether to end the process or loop back to the copywriter.
    """
    # Safety exit: if approved or max revisions (3) reached
    if state.get("is_approved") is True or state.get("revision_count", 0) >= 3:
        print("--- FLOW COMPLETE: APPROVED OR MAX ATTEMPTS REACHED ---")
        return END
    
    print(f"--- REJECTED BY CRITIC. ATTEMPT #{state.get('revision_count')}. RETRYING... ---")
    return "copywriter"

# --- GRAPH CONSTRUCTION ---

workflow = StateGraph(ReengageState)

# Nodes
workflow.add_node("analyst", call_analyst)
workflow.add_node("strategist", call_strategist)
workflow.add_node("copywriter", call_copywriter)
workflow.add_node("critic", call_critic)

# Linear Edges
workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "strategist")
workflow.add_edge("strategist", "copywriter")
workflow.add_edge("copywriter", "critic")

# Conditional Edge: The feedback loop
workflow.add_conditional_edges(
    "critic",
    decide_to_retry,
    {
        END: END,
        "copywriter": "copywriter"
    }
)

app_graph = workflow.compile()