# Codebase Structure

**Analysis Date:** 2026-03-17

## Directory Layout

```
ai-decision-engine/
├── main.py                          # FastAPI app, all HTTP endpoints
├── app/
│   ├── __init__.py
│   ├── core/                        # Configuration & infrastructure
│   │   ├── config.py                # DSPy init, env loading, provider routing
│   │   ├── security.py              # Auth middleware, CORS, access logging
│   │   ├── glm_caller.py            # GLM-4 API integration (receptionist sim)
│   │   └── check_dependencies.py    # Startup validation
│   ├── api/
│   │   └── reengagement.py          # Reengage endpoints (legacy?)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── sdr/                     # Sales Development Representatives
│   │   │   ├── state.py             # ConversationTurn, GatekeeperState, CloserState
│   │   │   ├── gatekeeper/          # Contact collection from clinic reception
│   │   │   │   ├── agent.py         # GatekeeperAgent (DSPy ChainOfThought)
│   │   │   │   ├── graph.py         # LangGraph workflow (detect_persona → process/process_menu_bot)
│   │   │   │   ├── signature.py     # GatekeeperSignature (SDR principles)
│   │   │   │   ├── persona_detector.py # PersonaDetector (receptionist/bot/ai/manager)
│   │   │   │   ├── menu_bot_agent.py   # MenuBotAgent (bypass menu structures)
│   │   │   │   ├── utils.py         # Helper functions (safe_str, etc)
│   │   │   │   ├── receptionist_sim.py # Synthetic receptionist via GLM-4
│   │   │   │   ├── conversation_eval.py # Conversation runner + scoring
│   │   │   │   └── __init__.py
│   │   │   ├── closer/              # Meeting scheduling with manager
│   │   │   │   ├── agent.py         # CloserAgent (DSPy ChainOfThought)
│   │   │   │   ├── graph.py         # LangGraph workflow (single node)
│   │   │   │   ├── signature.py     # CloserSignature (sales progression stages)
│   │   │   │   ├── utils.py         # Datetime parsing, phone cleaning
│   │   │   │   └── __init__.py
│   │   │   ├── test_sdr_agents.py   # Main test runner (49 cases, GPT-4o judge)
│   │   │   ├── test_full_conversation.py # Multi-turn test orchestration
│   │   │   ├── test_ab_gatekeeper.py # A/B testing harness
│   │   │   ├── test_ab_closer.py    # A/B testing harness
│   │   │   ├── optimize_gatekeeper.py # BootstrapFewShot optimizer
│   │   │   ├── analyze_gatekeeper_results.py # Result analysis
│   │   │   ├── analyze_closer_results.py    # Result analysis
│   │   │   ├── logs/                # Test execution logs ({timestamp}_{agent}_{model}.log)
│   │   │   └── __init__.py          # Exports gatekeeper_graph, closer_graph
│   │   ├── router/                  # Intent classification
│   │   │   ├── agent.py             # RouterAgent
│   │   │   ├── graph.py             # Single-node graph (classify_intentions)
│   │   │   ├── state.py             # RouterState, RouterRequest/Response
│   │   │   ├── test_router.py
│   │   │   └── __init__.py
│   │   └── reengage/                # Multi-agent lead reengagement
│   │       ├── analyst.py           # AnalystAgent (diagnoses pain points)
│   │       ├── strategist.py        # StrategistAgent (selects strategy)
│   │       ├── copywriter.py        # CopywriterAgent (generates copy)
│   │       ├── critic.py            # CriticAgent (scores & evaluates)
│   │       ├── graph.py             # LangGraph pipeline with conditional retry
│   │       ├── signatures.py        # All signatures for reengage agents
│   │       ├── state.py             # ReengageState
│   │       └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── name_cleaner.py          # extract_short_name() for clinic names
│   └── tests/
│       └── test_router.py           # Router unit tests
├── artifacts/
│   ├── .gitkeep
│   └── gatekeeper_optimized.json    # BootstrapFewShot demos (auto-loaded by agent)
├── supabase/
│   └── migrations/                  # Schema migrations
├── scripts/                         # Utility scripts (if any)
├── venv/                            # Python virtual environment
├── .env                             # Local development env vars
├── .claude/                         # Claude assistant config (GSD framework)
├── main.py                          # Entry point (symlink or actual)
├── railway.toml                     # Railway deployment config
└── CLAUDE.md                        # Project context (instructions)
```

## Directory Purposes

**`app/core/`:**
- Purpose: Foundational infrastructure — configuration, security, external integrations
- Contains: DSPy initialization, environment variable loading, API key routing, security middleware
- Key files: `config.py` (env loading + provider selection), `security.py` (middleware + API validation)

**`app/agents/sdr/gatekeeper/`:**
- Purpose: Agent for collecting manager contact from clinic reception via WhatsApp
- Contains: Agent logic, persona detection, menu bot bypass, receptionist simulation for testing
- Key files: `agent.py` (DSPy module), `signature.py` (130 lines of SDR principles), `graph.py` (LangGraph workflow)

**`app/agents/sdr/closer/`:**
- Purpose: Agent for scheduling meetings with clinic managers
- Contains: Agent logic, conversation progression (greeting → pitching → objection handling → scheduling)
- Key files: `agent.py` (DSPy module), `signature.py` (stage-based reasoning)

**`app/agents/router/`:**
- Purpose: Intent classifier — routes patient messages to specialized agents
- Contains: Single-node LangGraph that classifies message intentions
- Key files: `agent.py`, `graph.py` (minimal)

**`app/agents/reengage/`:**
- Purpose: Multi-agent pipeline for lead reengagement via tailored copy generation
- Contains: Analyst → Strategist → Copywriter → Critic chain with conditional retry
- Key files: `graph.py` (orchestration), individual agent files

**`app/utils/`:**
- Purpose: Shared utilities across agents
- Contains: Name extraction, string cleaning, validation helpers
- Key files: `name_cleaner.py` (extract clinic short names)

**`artifacts/`:**
- Purpose: Generated optimization artifacts
- Contains: `gatekeeper_optimized.json` (auto-generated by optimizer, auto-loaded by agent if present)
- Auto-loaded: Yes (GatekeeperAgent.__init__ checks existence and loads if found)

**`supabase/migrations/`:**
- Purpose: Database schema version control
- Contains: SQL migration files for Supabase tables (gk_conversations, gk_messages, gk_leads, gk_logs, etc)

## Key File Locations

**Entry Points:**

- `main.py` — FastAPI application with all HTTP endpoints (health, router, reengage, gatekeeper, closer)
- `app/agents/sdr/__init__.py` — Exports `gatekeeper_graph`, `closer_graph` for main.py to import
- `app/core/config.py:init_dspy()` — Called on startup to initialize LLM backend

**Configuration:**

- `app/core/config.py` — Environment loading, DSPy provider routing, settings singleton
- `.env` — Local environment variables (development only, EasyPanel overrides in production)
- `railway.toml` — Railway deployment configuration

**Core Logic:**

- `app/agents/sdr/gatekeeper/agent.py` — GatekeeperAgent with output cleaning
- `app/agents/sdr/gatekeeper/graph.py` — Orchestrates detect_persona → process routing
- `app/agents/sdr/gatekeeper/signature.py` — 130-line DSPy signature with SDR principles
- `app/agents/sdr/closer/agent.py` — CloserAgent with meeting datetime parsing

**Testing:**

- `app/agents/sdr/test_sdr_agents.py` — Main test runner (CLI: `python -m app.agents.sdr.test_sdr_agents --gatekeeper`)
- `app/agents/sdr/test_gatekeeper_cases.json` — 49 test cases (41 synthetic, 8 real)
- `app/agents/sdr/gatekeeper/conversation_eval.py` — Conversation orchestration + scoring
- `app/agents/sdr/gatekeeper/receptionist_sim.py` — Synthetic receptionist via GLM-4
- `app/agents/sdr/optimize_gatekeeper.py` — BootstrapFewShot optimizer

**Utilities:**

- `app/utils/name_cleaner.py` — `extract_short_name()` for clinic name extraction
- `app/core/security.py` — Security middleware, auth, logging
- `app/core/glm_caller.py` — GLM-4 API client (isolated for receptionist simulator)

## Naming Conventions

**Files:**

- Agent modules: `{agent_name}.py` (e.g., `agent.py`, `persona_detector.py`, `menu_bot_agent.py`)
- Signatures: `signature.py` (always lowercase, one per agent type or shared in `signatures.py`)
- Graphs: `graph.py` (LangGraph workflow definitions)
- States: `state.py` (Pydantic models and TypedDict schemas)
- Tests: `test_{feature}.py` or `{feature}_test.py`
- Utilities: `utils.py` (helpers specific to module)
- Configuration: `config.py` (app-wide), `settings.json` (optional env-specific)

**Directories:**

- Agent type directories: `{agent_type}/` under `app/agents/` (e.g., `sdr/`, `router/`, `reengage/`)
- Sub-agent directories: `{sub_agent}/` under `app/agents/{agent_type}/` (e.g., `gatekeeper/`, `closer/`)
- Logs: `logs/` under `app/agents/sdr/` for test execution logs

**Functions & Classes:**

- Agent classes: `{Name}Agent` (e.g., `GatekeeperAgent`, `CloserAgent`, `RouterAgent`)
- Signature classes: `{Name}Signature` (e.g., `GatekeeperSignature`, `PersonaDetectorSignature`)
- State types: `{Name}State` (e.g., `GatekeeperState`, `RouterState`, `ReengageState`)
- Graph nodes: `snake_case` (e.g., `detect_persona`, `process`, `classify_intentions`)
- Request models: `{Name}Request` (e.g., `GatekeeperRequest`, `RouterRequest`)
- Response models: `{Name}Response` (e.g., `GatekeeperResponse`, `RouterResponse`)

## Where to Add New Code

**New SDR Agent (like Gatekeeper/Closer):**
- Primary code: `app/agents/sdr/{new_agent}/`
  - Create: `agent.py`, `graph.py`, `signature.py`, `state.py`
  - Add imports to `app/agents/sdr/__init__.py`
  - Add endpoint to `main.py` following pattern of existing endpoints
- Tests: `app/agents/sdr/test_{new_agent}.py`
- Cases: `app/agents/sdr/test_{new_agent}_cases.json`

**New Specialist Agent (like Router/Reengage):**
- Primary code: `app/agents/{agent_type}/`
  - Create: `agent.py`, `graph.py`, `state.py`, and any supporting modules
  - Add imports to `app/agents/{agent_type}/__init__.py`
  - Add endpoint to `main.py`
- Tests: `app/agents/{agent_type}/test_{feature}.py`

**New Utility Function:**
- Shared across agents: `app/utils/{function_category}.py`
- Agent-specific: `app/agents/{agent_type}/{agent}/utils.py`

**New Middleware or Core Logic:**
- HTTP middleware: `app/core/middleware_{name}.py` or add to `security.py`
- Configuration: Add settings to `app/core/config.py` (EasyScaleSettings class)
- External integrations: `app/core/{service}_caller.py` (e.g., `glm_caller.py` for GLM-4)

**Test Cases:**
- Always add to corresponding `test_{feature}_cases.json` file
- Format: JSON array of case objects with: scenario, clinic_name, reception_message, expected_stage, etc.
- Run: `python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases`

## Special Directories

**`artifacts/`:**
- Purpose: Auto-generated optimization artifacts
- Generated: Yes (by `optimize_gatekeeper.py` via BootstrapFewShot)
- Committed: `.gitkeep` committed, `gatekeeper_optimized.json` typically in `.gitignore` (regenerated per session)
- Auto-loaded: GatekeeperAgent checks for `artifacts/gatekeeper_optimized.json` on init

**`supabase/migrations/`:**
- Purpose: Database schema version control
- Generated: No (manually created)
- Committed: Yes, all migration files
- Usage: Supabase CLI applies migrations to database

**`app/agents/sdr/logs/`:**
- Purpose: Test execution logs
- Generated: Yes (by test runners)
- Committed: No (in `.gitignore`)
- Format: `{timestamp}_{agent}_{provider}_{model}.log`

**`venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (by `python -m venv venv`)
- Committed: No (in `.gitignore`)

**`.claude/`:**
- Purpose: Claude assistant configuration (GSD framework - get-shit-done)
- Contents: Custom commands, agents, hooks, project settings
- Committed: Yes (except local overrides)

---

*Structure analysis: 2026-03-17*
