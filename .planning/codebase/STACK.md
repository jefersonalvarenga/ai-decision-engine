# Technology Stack

**Analysis Date:** 2026-03-17

## Languages

**Primary:**
- Python 3.11.9 - Backend API and agent orchestration
- Python 3.9 (legacy) - Older venv present (phased out)

**Configuration Files:**
- YAML - Deployment configs
- JSON - Test cases, optimized demos, environment configuration

## Runtime

**Environment:**
- Python 3.11.9 - Specified in `.python-version` and `runtime.txt`
- Uvicorn 0.31.0 - ASGI server for FastAPI
- Deployed on Railway (NIXPACKS builder) and Easypanel

**Package Manager:**
- pip - Python package management
- No lockfile (requirements.txt is the source of truth)

## Frameworks

**Core API:**
- FastAPI 0.115.0 - HTTP API framework for n8n integration
- Pydantic 2.9.2 - Data validation and settings management
- Pydantic-Settings 2.5.2 - Environment configuration handling

**Agent Orchestration:**
- DSPy 2.5.43 - LLM optimization and prompt management (version constraint: see requirements.txt)
- LangGraph 0.2.60 - Agentic graph workflows and state management

**Testing:**
- Built-in Python `unittest`/`pytest` patterns (see `test_sdr_agents.py`, `test_router.py`)

**Build/Dev:**
- Docker - Containerization (Dockerfile uses python:3.11-slim)
- python-dotenv 1.0.1 - Environment variable loading (.env support)

## Key Dependencies

**Critical:**
- anthropic 0.40.0 - Claude LLM API client (configurable provider, currently Haiku 4.5 in prod)
- openai 1.57.2 - OpenAI API client (for GPT-4o test judge and gpt-4o-mini fallback)
- groq 0.12.0 - Groq Llama models support (optional provider)

**Infrastructure:**
- supabase 2.10.0 - PostgreSQL client for gk_logs, gk_conversations, gk_leads tables
- psycopg[binary] 3.2.13 - PostgreSQL adapter for Supabase
- httpx 0.27.2 - Async HTTP client for Supabase REST API and webhook calls

**Additional LLM Providers:**
- GLM support (via config, uses BigModel API: `glm-4.7-flash`)
- XAI support (via config, uses X.AI API)
- Gemini support (via config)

## Configuration

**Environment:**
- `.env` file (local development) - Contains DSPY_PROVIDER, API keys, Supabase credentials
- `.env.example` - Template with all required variables
- EasyPanel environment variables (production) - Override .env via Pydantic settings (`override=False`)
- Settings priority: EasyPanel env vars > .env file > defaults in code

**Key Configuration:**
- `DSPY_PROVIDER` - LLM provider selection (openai/anthropic/groq/xai/glm/gemini)
- `DSPY_MODEL` - Model name for agents (default: gpt-4o-mini, prod: claude-haiku-4-5)
- `DSPY_TEMPERATURE` - Prompt sampling (default: 0.3)
- `DSPY_MAX_TOKENS` - Max completion length (default: 1000)
- `SUPABASE_URL`, `SUPABASE_KEY` - Database connection
- `API_KEY` - Optional FastAPI authentication token

**Build:**
- `Dockerfile` - Multi-stage build, PYTHONPATH=/app, uvicorn entrypoint
- `railway.toml` - Railway.app deployment manifest (NIXPACKS builder)
- `Procfile` - Heroku-style process definition (uvicorn on $PORT)

## Platform Requirements

**Development:**
- Python 3.11.9 (or 3.9 for legacy)
- pip with 18+ MB cache for dependencies
- Optional: Docker for containerized development

**Production:**
- Deployment target: Easypanel (primary), Railway, or Heroku-compatible platforms
- Health check endpoint: `/v1/health`
- Port: 8000
- Memory: ~500MB minimum (DSPy + LangGraph state)
- Requires: OPENAI_API_KEY or ANTHROPIC_API_KEY (depending on DSPY_PROVIDER)

## LLM Model Configuration

**Main Agent Model (Configurable):**
- Current (prod): `anthropic/claude-haiku-4-5-20251001`
- Alternative: `openai/gpt-4o-mini`
- Alternative: `groq/llama-3.3-70b-versatile`

**Dedicated Test Judge (Fixed):**
- `openai/gpt-4o` - Used in `test_sdr_agents.py` for evaluating agent responses
- Separate from main model to ensure consistency in test evaluation

**Receptionist Simulator (Isolation):**
- Configurable via `RECEPTIONIST_MODEL` (default: `openai/glm-4.7-flash`)
- Separate LM instance from main SDR model
- API: BigModel (GLM) or compatible OpenAI interface

---

*Stack analysis: 2026-03-17*
