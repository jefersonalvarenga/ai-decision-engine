# Architecture

**Analysis Date:** 2026-03-17

## Pattern Overview

**Overall:** Stateless multi-agent system with LangGraph orchestration

**Key Characteristics:**
- FastAPI HTTP stateless layer — receives context from n8n, returns structured actions
- LangGraph state machines orchestrate multi-turn agent workflows
- DSPy-based agents with ChainOfThought reasoning for LLM decisions
- Zero determinism principle — all behavior flows through LLM (no hardcoded business logic)
- n8n responsible for persistence, messaging, and historical context
- Fire-and-forget async logging to Supabase (gk_logs table)

## Layers

**HTTP API Layer:**
- Purpose: FastAPI endpoints that expose agent workflows to n8n via webhooks
- Location: `main.py` (entry point, all endpoints)
- Contains: Request/response models, endpoint handlers, startup initialization
- Depends on: Agent graphs, DSPy configuration, Supabase client
- Used by: n8n workflow (inbound/outbound webhooks)

**Agent Orchestration Layer (LangGraph):**
- Purpose: Manages multi-turn conversational workflows as state machines
- Location: `app/agents/{agent_type}/graph.py` files
- Contains: Graph definition, node functions, conditional routing
- Depends on: Agent modules, state definitions
- Used by: HTTP layer to invoke full workflows
- Key graphs:
  - `app/agents/sdr/gatekeeper/graph.py` — manager contact collection workflow
  - `app/agents/sdr/closer/graph.py` — meeting scheduling workflow
  - `app/agents/router/graph.py` — intent classification workflow
  - `app/agents/reengage/graph.py` — multi-stage lead reengagement workflow

**Agent Processing Layer (DSPy):**
- Purpose: Individual agent modules that make LLM decisions
- Location: `app/agents/{agent_type}/agent.py` files
- Contains: DSPy ChainOfThought modules, prompt signatures, output parsing
- Depends on: Signatures, LLM backend (configured via DSPy)
- Used by: Graph nodes for single-turn processing
- Key agents:
  - `GatekeeperAgent` — contacts reception, extracts manager contact
  - `CloserAgent` — contacts manager, schedules meetings
  - `RouterAgent` — classifies patient message intentions
  - `MenuBotAgent` — attempts to bypass menu bots
  - Reengage agents: AnalystAgent, StrategistAgent, CopywriterAgent, CriticAgent

**State & Definition Layer:**
- Purpose: Defines conversation state structures and DSPy signatures
- Location: `app/agents/{agent_type}/state.py`, `app/agents/{agent_type}/signature.py`
- Contains: TypedDict state schemas, Pydantic models, DSPy Signature docstrings
- Depends on: Python typing, Pydantic, DSPy
- Used by: Graphs, agents, API endpoints
- Key files:
  - `app/agents/sdr/state.py` — GatekeeperState, CloserState, ConversationTurn
  - `app/agents/sdr/gatekeeper/signature.py` — GatekeeperSignature (130 lines, SDR principles)
  - `app/agents/sdr/gatekeeper/persona_detector.py` — PersonaDetectorSignature

**Utilities & Cross-Cutting:**
- Purpose: Shared helpers, configuration, security
- Location: `app/core/`, `app/utils/`
- Contains:
  - `config.py` — DSPy initialization, environment loading, provider routing
  - `security.py` — API key validation, CORS middleware, access logging
  - `name_cleaner.py` — extract short clinic names from Google Maps
  - `glm_caller.py` — GLM-4 integration (receptionist simulator)

**Testing & Evaluation:**
- Purpose: Conversation simulation, agent scoring, optimization
- Location: `app/agents/sdr/`
- Contains:
  - `test_sdr_agents.py` — runs 49 test cases against agents (GPT-4o judge)
  - `test_full_conversation.py` — multi-turn conversation runner
  - `optimize_gatekeeper.py` — BootstrapFewShot optimizer
  - `receptionist_sim.py` — synthetic receptionist via GLM-4
  - `conversation_eval.py` — scoring rubric and multi-turn orchestration

## Data Flow

**Gatekeeper Flow (Manager Contact Collection):**

1. n8n sends `GatekeeperRequest` to `POST /v1/sdr/gatekeeper`
2. FastAPI validates clinic_name, applies deterministic opt-out rules
3. `gatekeeper_graph.invoke()` executes state machine:
   - `detect_persona` node: PersonaDetector classifies who responded (receptionist/bot/ai/manager/unknown)
   - Route decision: if menu_bot → `process_menu_bot` node, else → `process` node
   - `process_menu_bot` (MenuBotAgent): attempts to bypass menu structures
   - `process` (GatekeeperAgent): conducts SDR conversation (requesting stage → handling_objection → success/failed)
4. Agent returns structured dict with: response_message, conversation_stage, extracted_manager_contact, should_send_message, approach_used, reasoning
5. FastAPI wraps result in `GatekeeperResponse`, fires async log to Supabase
6. n8n receives response, decides: should_send_message → route to Evolution API → persist in gk_messages/gk_conversations/gk_leads

**Closer Flow (Meeting Scheduling):**

1. n8n sends `CloserRequest` with manager contact details
2. FastAPI computes attempt_count from conversation_history
3. `closer_graph.invoke()` executes state machine:
   - Single node `process_closer` (CloserAgent): runs ChainOfThought against manager
   - Agent analyzes: greeting stage → presenting → objection_handling → scheduling → scheduled/lost
4. Agent returns: response_message, conversation_stage, meeting_datetime (if confirmed), should_send_message
5. FastAPI wraps in `CloserResponse`
6. n8n: if meeting_datetime → create Google Calendar event, else persist message

**Router Flow (Intent Classification):**

1. n8n sends `RouterRequest` with latest patient message + history
2. `router_graph.invoke()` — single node `classify_intentions`
3. RouterAgent returns: intentions (list), confidence, reasoning
4. n8n uses intentions to route to appropriate specialized agents (booking, intake, escalation, etc.)

**Reengage Flow (Multi-Agent Copy Generation):**

1. n8n sends `ReengageRequest` with lead profile + psychographic data
2. `reengage_graph.invoke()` executes multi-stage pipeline:
   - `call_analyst` (AnalystAgent): diagnoses lead's pain points
   - `call_strategist` (StrategistAgent): selects messaging strategy
   - `call_copywriter` (CopywriterAgent): generates final copy
   - `call_critic` (CriticAgent): evaluates and scores copy quality
   - `decide_to_retry`: if rejected, loops back to copywriter (max 3 revisions)
3. Returns: generated_copy, selected_strategy, revision_count

**State Management:**

- **Request state:** Comes from n8n — conversation history, latest message, clinic/manager details, time context
- **Graph state:** Persisted within LangGraph execution (current_turn only) — passed between nodes
- **Conversation history:** Managed by n8n in Supabase (gk_messages, gk_conversations)
- **Logs:** Fire-and-forget async to gk_logs (non-blocking, diagnostic only)

## Key Abstractions

**Persona (Classification):**
- Purpose: Route message handling based on who responded (receptionist vs bot vs manager)
- Examples: `app/agents/sdr/gatekeeper/persona_detector.py`
- Pattern: LLM evaluates latest_message against priority rules (waiting → menu_bot → ai_assistant → call_center → manager → receptionist → unknown)
- Runs every turn — no caching

**Signature (Prompt Template):**
- Purpose: DSPy Signature defines LLM input/output contract
- Examples: `app/agents/sdr/gatekeeper/signature.py` (SDR principles, 130 lines)
- Pattern: Docstring contains all instructions (personas, tactics, constraints, examples)
- Output fields typed with validation (regex for phone, email validation)

**Agent Module (DSPy.Module):**
- Purpose: Wraps signature + ChainOfThought reasoning
- Examples: `GatekeeperAgent`, `CloserAgent`, `MenuBotAgent`
- Pattern: `__init__` loads signature + optional few-shot demos, `forward()` calls DSPy chain, returns dict with cleaned outputs
- Optimization: Auto-loads `artifacts/gatekeeper_optimized.json` if exists (BootstrapFewShot demos)

**Graph Node (Function):**
- Purpose: Stateless function that transforms graph state
- Examples: `detect_persona()`, `process()`, `classify_intentions()`
- Pattern: Takes state dict, calls agent/external service, returns dict with state updates
- Routing: Conditional edges determine next node based on output fields

**Request/Response Models (Pydantic):**
- Purpose: Validate and serialize HTTP payloads
- Pattern: BaseModel with Field descriptions for n8n documentation
- Validation: Happens at FastAPI layer before graph invocation

## Entry Points

**HTTP POST /v1/sdr/gatekeeper:**
- Location: `main.py:326`
- Triggers: n8n inbound/outbound webhooks (new clinic or new message)
- Responsibilities: Validate request, invoke gatekeeper_graph, log result, return response

**HTTP POST /v1/sdr/closer:**
- Location: `main.py:437`
- Triggers: n8n when Closer workflow starts
- Responsibilities: Count attempts, invoke closer_graph, handle datetime parsing, return response

**HTTP POST /v1/router:**
- Location: `main.py:262`
- Triggers: n8n patient message router
- Responsibilities: Invoke router_graph, return intent classifications

**HTTP POST /v1/reengage:**
- Location: `main.py:295`
- Triggers: n8n for dormant leads
- Responsibilities: Invoke reengage_graph with psychographic context, return generated copy

**Startup Event:**
- Location: `main.py:218`
- Triggers: When server starts
- Responsibilities: `init_dspy()` — loads API keys, configures LLM backend from environment

## Error Handling

**Strategy:** Deterministic validation before LLM, graceful degradation in LLM processing

**Patterns:**

- **Pre-flight validation (main.py):** clinic_name empty → HTTPException 422; opted_out status → silent skip
- **Provider routing (config.py):** Unknown provider → fallback to console print warning, agent uses default
- **Output cleaning (agent.py):** Regex validation for phone (10+ digits), email (@ format), name (strip whitespace)
- **Graph exception handling (graph.py):** Try/except in node wrappers, return default dict if agent fails
- **Rate limit retry (conversation_eval.py):** Exponential backoff with random jitter for API calls
- **Async logging (main.py):** Fire-and-forget to Supabase — network errors don't block response

## Cross-Cutting Concerns

**Logging:**
- Primary: Async fire-and-forget to `gk_logs` table via Supabase REST API
- Secondary: Console prints (DSPy agent reasoning, LangGraph node execution)
- Approach: `_log_gk()` called after graph result, captures: persona, stage, approach, reasoning, processing_time_ms

**Configuration:**
- Environment: EasyPanel env vars override .env local (via pydantic-settings)
- DSPy initialization: `init_dspy()` configures provider (anthropic/openai/groq/etc) + model + keys
- Support for multiple LLM backends: Anthropic, OpenAI, Groq, Gemini, xAI, GLM (receptionist simulator isolated)

**Validation:**
- Input: Pydantic models (FastAPI automatic)
- Output: Regex cleaning in agent.py (phone/email/name), enum literals in signatures
- Stage progression: Defined as literal types in GatekeeperOutput, CloserOutput

**Determinism Avoidance:**
- Zero hardcoded business logic — all "if this → do that" flows through LLM
- Exception: Format validation (regex for phone/email) and Supabase status checks (opt-out)
- Philosophy: LLM learns patterns from few-shot demos and signature instructions

---

*Architecture analysis: 2026-03-17*
