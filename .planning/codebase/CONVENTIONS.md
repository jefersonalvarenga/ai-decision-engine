# Coding Conventions

**Analysis Date:** 2025-03-17

## Naming Patterns

**Files:**
- Python modules use `snake_case`: `gatekeeper_agent.py`, `persona_detector.py`, `test_sdr_agents.py`
- Agent implementations in `app/agents/{domain}/{agent_type}/` with clear layering
- Test files: `test_*.py` or `{module}_test.py` pattern
- Utility files: `utils.py` in the same package as the module they support
- DSPy signature files: `signature.py` (singular) in agent directories

**Functions:**
- `snake_case` for all functions: `detect_persona()`, `invoke_agent()`, `safe_str()`
- Private functions prefixed with underscore: `_clean_phone()`, `_block_ip()`, `_get_api_key()`
- Test functions prefixed with `test_`: `test_sales_intent_basic()`, `test_graph_builds_successfully()`
- Helper functions in classes also use underscore: `_should_log()`, `_parse_datetime()`

**Variables:**
- `snake_case` for all variables: `clinic_name`, `conversation_history`, `extracted_contact`
- Constants in `UPPER_SNAKE_CASE`: `MAX_ATTEMPTS`, `SUSPICIOUS_PATHS`, `DEPLOY_COMMIT`
- Private variables prefixed with underscore: `_ARTIFACT_PATH`, `_judge_lm`, `_settings`
- Acronyms preserve intent: `api_key` (not `apiKey`), `gk_logs` (Gatekeeper logs)

**Types:**
- Pydantic models in `PascalCase`: `GatekeeperRequest`, `GatekeeperResponse`, `PersonaDetectorSignature`
- DSPy signatures in `PascalCase` with `Signature` suffix: `GatekeeperSignature`, `MenuBotSignature`
- TypedDict classes in `PascalCase`: `GatekeeperState`, `CloserState`
- Enum/Literal values in `snake_case`: `"direct" | "feedback" | "referral"`, `"requesting" | "handling_objection"`

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `.eslintrc`, or `pyproject.toml` present)
- Code follows PEP 8 conventions with occasional long docstrings
- Docstrings use triple quotes (`"""`) and describe purpose, not obvious actions
- Multi-line constructs use natural line breaks

**Linting:**
- No active linter config detected (no ESLint, Pylint, or Flake8 config files)
- Code relies on manual discipline and PyCharm/IDE defaults
- Type hints present but not strictly enforced at runtime

**Import Organization:**
Order follows standard Python pattern:
1. Standard library imports: `import os, sys, time, json, asyncio, re, etc.`
2. Third-party imports: `import dspy, fastapi, pydantic, langgraph, httpx, etc.`
3. Local imports: `from app.core.config import get_settings`, `from .agent import GatekeeperAgent`

Path aliases:
- None explicitly configured; all imports use relative (`from .utils`) or absolute (`from app.agents.sdr...`) paths
- Root directory utilities: `sys.path.insert(0, str(ROOT_DIR))` pattern used in test runners

## Error Handling

**Patterns:**
- Silent failures with fallback defaults preferred in non-critical paths
  - Example: `_clean_phone()` returns `None` if regex fails, never raises
  - Example: `gk_log` failure is printed but continues: `print(f"[gk_log] falhou (não crítico): {e}")`

- Try/except blocks without bare `except` — specific exception types caught:
  ```python
  try:
      self.load(str(self._ARTIFACT_PATH))
  except Exception as e:
      print(f"⚠️  GatekeeperAgent: falha ao carregar {self._ARTIFACT_PATH.name} — {e}")
  ```

- FastAPI HTTPException for API contract violations:
  - 422 Unprocessable Entity for missing required fields (clinic_name)
  - 401 Unauthorized for invalid API keys
  - 429 Too Many Requests for rate limit violations

- LLM output validation: format-based fallback, never hard error
  - `safe_str()` utility converts any type to string with default fallback
  - Invalid stage values logged with warning, value retained as-is (not crashed)
  - Phone/email extraction uses regex validation with `None` return on failure

**Defensive Coding:**
- Optional type hints throughout: `Optional[str]`, `Optional[dict]`
- Default fallback values in DSPy.InputField descriptions and config
- Validation happens in agent `forward()` methods, not in signatures

## Logging

**Framework:** `print()` calls (no structured logging library)

**Patterns:**
- Prefix style: emoji + component name + action
  - `✅` (success): `"✅ GatekeeperAgent: demos otimizados carregados (50KB)"`
  - `❌` (error): `"❌ Failed to initialize DSPy: {e}"`
  - `⚠️` (warning): `"⚠️ GatekeeperAgent: falha ao carregar artifact — {e}"`
  - `🚀` (startup): `"🚀 EasyScale Clinic API starting..."`
  - `---` (flow markers): `"--- PERSONA DETECTOR: Classificando resposta da clínica ---"`
  - `📊` (metrics): `"📊 GET /v1/gatekeeper → 200 (145ms) [192.168.1.1]"`

- No log level configuration; all output to `print()` which FastAPI/Uvicorn captures
- `TeeLogger` class duplicates stdout to file: used in test runners to capture results to `logs/{timestamp}_{agent}_{provider}_{model}.log`
- Verbose DSPy execution logs in development (persona detection, agent decisions)

## Comments

**When to Comment:**
- Explain "why" not "what": the code should be clear about what it does
- Algorithm intent: `# Lazy import to avoid circular dependency at module load time`
- Non-obvious business logic: `# Promoção de stage para success quando contato foi extraído (validação de formato)`
- Workaround explanations: `# GLM-5 occasionally returns non-string types for str fields`

**JSDoc/TSDoc:**
- DSPy signatures use extensive docstrings (100+ lines) to embed full behavior rules
  - Triple-quoted markdown-style docstrings with sections and examples
  - Sections: `## TÁTICAS DISPONÍVEIS`, `## LIDANDO COM RESISTÊNCIA`, `## CONTATO VÁLIDO`
  - Used as prompt material — precision is critical

- Function docstrings brief and purposeful:
  ```python
  def safe_str(val, default: str = "") -> str:
      """
      Safely convert any DSPy output field to string.
      GLM-5 occasionally returns non-string types (int, list, None)
      for fields declared as str in the DSPy Signature.
      """
  ```

- Pydantic model Field descriptions used as documentation:
  ```python
  clinic_name: str = Field(..., description="Nome da clínica")
  conversation_history: List[ConversationTurn] = Field(
      default_factory=list,
      description="Histórico da conversa [{role, content, stage, approach_used}]"
  )
  ```

## Function Design

**Size:** Functions are typically 10-50 lines; longer functions break into:
- Setup phase (validate inputs, prepare state)
- Processing phase (core logic, usually delegated to modules)
- Output phase (format result, cleanup)

Example: `GatekeeperAgent.forward()` (`59-111` in `agent.py`):
1. Call DSPy module
2. Extract and clean outputs (3 separate `_clean_*()` calls)
3. Validate stage and promote to success if contact found
4. Return dict with all fields

**Parameters:**
- `Optional[str]` / `Optional[int]` for parameters with sensible defaults
- Explicit defaults in function signature: `sdr_name: str = "Vera"`
- No `**kwargs` pattern; all parameters explicitly listed

**Return Values:**
- Dictionaries from agent `forward()` methods: `{"response_message": "...", "conversation_stage": "requesting", ...}`
- Pydantic models from FastAPI endpoints: `GatekeeperResponse`, `RouterResponse`
- `None` for failed optional operations (not exceptions)
- Tuples rare; structured returns via dict or model preferred

## Module Design

**Exports:**
- `__init__.py` files import key components and expose them at package level
  - Example: `from .graph import app_graph as gatekeeper_graph` in `app/agents/sdr/gatekeeper/__init__.py`
  - Allows `from app.agents.sdr import gatekeeper_graph` in main.py

- Private modules (prefixed `_`) not exported
- Singletons instantiated at module level in graph files:
  ```python
  gatekeeper_agent = GatekeeperAgent()
  persona_detector = PersonaDetector()
  ```

**Barrel Files:**
- Not consistently used for re-exports
- Main imports happen at: `main.py` (FastAPI app setup), `graph.py` files (LangGraph setup)
- Circular import avoidance via lazy imports in config: `from app.core.config import get_settings` (not at module load)

## Language Conventions

**Codebase Language:** Portuguese and English mixed

- **DSPy Signatures:** Portuguese ("Você é uma SDR mulher da EasyScale...")
  - Reflects that prompts are in Portuguese for Brazilian CLI audience
  - User-facing strings in signature are Portuguese

- **Code Structure:** English
  - Variable names: `clinic_name`, `detected_persona`, `conversation_stage`
  - Class/function names: `GatekeeperAgent`, `PersonaDetector`, `MenuBotAgent`
  - Comments and docstrings: English in utility code, Portuguese in agent logic

- **Output Strings:** Mixed (Portuguese for user messages, English for system logs)
  - LLM responses: Portuguese (natural WhatsApp conversation)
  - System logs: English (`"✅ DSPy Motor initialized with..."`
  - Error messages: Portuguese in signatures, English in utilities

## Zero Determinism Principle

**Core Convention:** All behavior passes through LLM. No hardcoded if/else for business logic.

- **Removed patterns (no longer used):**
  - `WAIT_PATTERNS`, `IMMEDIATE_REJECTION_PATTERNS`, `MAX_BYPASS_ATTEMPTS` (previous versions)
  - Attempt counters forcing specific behavior (now LLM decides via prompt)
  - Role-based routing without LLM analysis (now `PersonaDetector` runs every turn)

- **Allowed exceptions:**
  - Format validation: `re.sub(r"\D", "", phone)` to clean phone numbers
  - Regex checks: `@` in email validation
  - Enum validation: stage must be in `["requesting", "handling_objection", "success", "failed"]`

- **Implementation:** All personalization, objection handling, stage progression decided by DSPy signatures

---

*Convention analysis: 2025-03-17*
