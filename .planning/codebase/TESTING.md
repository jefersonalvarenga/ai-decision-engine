# Testing Patterns

**Analysis Date:** 2025-03-17

## Test Framework

**Runner:**
- No pytest, unittest, or vitest configuration file present
- Custom test runner: `app/agents/sdr/test_sdr_agents.py` (TeeLogger-based system)
- FastAPI testing: Pydantic models used for request/response validation, no explicit test framework

**Assertion Library:**
- Custom assertions in test runners (not pytest.assert)
- DSPy/LLM based evaluation via `judge_gatekeeper_response()` using GPT-4o as judge
- Manual assertion pattern: `assert condition, f"error message"`

**Run Commands:**
```bash
# Test Gatekeeper agent with pending cases only
python -m app.agents.sdr.test_sdr_agents --gatekeeper

# Test Gatekeeper agent with all cases
python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases

# Test specific case by number
python -m app.agents.sdr.test_sdr_agents --gatekeeper --case 3

# Test N cases total
python -m app.agents.sdr.test_sdr_agents --gatekeeper --n 5

# Interactive testing mode
python -m app.agents.sdr.test_sdr_agents --interactive

# Optimize agent with BootstrapFewShot (runs test cases as metric)
python -m app.agents.sdr.optimize_gatekeeper

# With optimization options
python -m app.agents.sdr.optimize_gatekeeper --max-demos 8 --delay 1.0 --skip-validate

# Warm-start optimization (improve existing artifact)
python -m app.agents.sdr.optimize_gatekeeper --warm-start
```

## Test File Organization

**Location:**
- Test cases: `app/agents/sdr/test_gatekeeper_cases.json` and `test_closer_cases.json` (JSON-based)
- Test runners: `app/agents/sdr/test_sdr_agents.py`, `test_ab_gatekeeper.py`, `test_ab_closer.py`
- Analysis scripts: `analyze_gatekeeper_results.py`, `analyze_closer_results.py`
- Optimization scripts: `optimize_gatekeeper.py`
- Router tests: `app/tests/test_router.py` (pytest style)
- Full conversation tests: `app/agents/sdr/test_full_conversation.py`

**Naming:**
- Test case JSON: singular entity type (`test_gatekeeper_cases.json`)
- Runner scripts: `test_*.py` or `{agent}_test.py`
- A/B testing: `test_ab_*.py` (runs same cases against two models)
- Result analysis: `analyze_*_results.py` (processes test output)

**Structure:**
```
app/agents/sdr/
  test_sdr_agents.py              # Main test runner with logging
  test_gatekeeper_cases.json      # 49 cases: 41 synthetic + 8 real
  test_closer_cases.json          # Closer agent cases
  optimize_gatekeeper.py          # BootstrapFewShot optimizer
  test_ab_gatekeeper.py           # Compare two models
  analyze_gatekeeper_results.py   # Parse test logs
  logs/                           # Test output directory
    20250317_143025_gatekeeper_anthropic_claude-haiku-4-5.log
    20250317_143025_gatekeeper_openai_gpt-4o.log
  gatekeeper/
    agent.py
    signature.py
    graph.py
    test_sdr_agents.py            # Imported by test_sdr_agents.py
```

## Test Structure

**Suite Organization:**

```python
# From test_sdr_agents.py (Gatekeeper tests)
# Tests organized by case, not by function
for case_idx, case in enumerate(cases_to_run):
    print(f"\n--- Case {case_idx + 1}/{len(cases_to_run)} ---")
    print(f"Clínica: {case['clinic_name']}")
    print(f"Esperado: {case['expected_stage']}")

    # Setup
    result = agent(
        clinic_name=case["clinic_name"],
        conversation_history=case.get("conversation_history", []),
        latest_message=case.get("latest_message"),
        current_hour=case.get("current_hour", 10),
        current_weekday=case.get("current_weekday", 1),
        detected_persona=case.get("detected_persona", "receptionist"),
    )

    # Evaluate with judge
    verdict = judge_gatekeeper_response(case, result)

    # Assert
    if verdict["valid"]:
        passed += 1
        print(f"✅ PASS")
    else:
        failed += 1
        print(f"❌ FAIL: {verdict['reason']}")
```

From `test_router.py` (pytest style):
```python
class TestIntentClassification:
    """Test intent detection from PT-BR messages."""

    def test_sales_intent_basic(self, base_state):
        """Test basic sales inquiry detection."""
        messages = ["quanto custa o botox?", "tem desconto?"]
        for msg in messages:
            state = {**base_state, "latest_message": msg}
            assert IntentType.SALES.value in [IntentType.SALES.value]
```

**Patterns:**

**Setup pattern:**
- Fixture-based for pytest (see `app/tests/test_router.py`):
  ```python
  @pytest.fixture
  def sample_context():
      """Standard patient context for testing."""
      return {
          "patient_id": "p_test_001",
          "active_items": [...],
          "behavioral_profile": {...}
      }
  ```

- Dictionary-based for custom runners:
  ```python
  case = {
      "clinic_name": "Clínica Tayná",
      "conversation_history": [...],
      "latest_message": "Qual é o assunto?",
      "expected_stage": "handling_objection"
  }
  ```

**Teardown pattern:**
- No explicit teardown (tests are stateless)
- File cleanup: test logs written to `logs/` directory, kept for analysis
- Artifact management: `optimize_gatekeeper.py` validates before overwriting `artifacts/gatekeeper_optimized.json`

**Assertion pattern:**
- DSPy judge-based: `assert verdict["valid"], verdict["reason"]`
- Manual: `assert result["conversation_stage"] == "success"`
- JSON case validation: Pydantic models validate request/response structure
- Logic validation: Judge LLM (GPT-4o) compares output against strategy document

## Mocking

**Framework:** `unittest.mock` (Python stdlib)

**Patterns:**

```python
# From test_router.py
from unittest.mock import Mock, patch

@patch('router_agent.RouterModule')
def test_graph_execution_flow(self, mock_router, sample_context):
    """Test basic graph execution flow."""
    mock_prediction = Mock()
    mock_prediction.intents = [IntentType.SALES.value]
    mock_prediction.urgency_score = 2
    mock_prediction.reasoning = "Customer asking about price"

    mock_router.return_value.forward.return_value = mock_prediction

    graph = build_easyscale_graph()
    # ... test continues
```

**What to Mock:**
- External LLM calls: replace DSPy modules with Mock objects returning expected outputs
- Database queries: mock Supabase responses (not done in current codebase — agents are stateless)
- File I/O: mock artifact loading in agent tests

**What NOT to Mock:**
- Gatekeeper/Closer agents themselves (testing real LLM output quality)
- DSPy signatures (prompt behavior is production behavior)
- Persona detector (needs to run against real conversation patterns)
- Graph flow (routing logic must work end-to-end)

## Fixtures and Factories

**Test Data:**

```python
# From test_sdr_agents.py — load from JSON
def load_cases() -> list:
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)

# From test_router.py — inline dict fixtures
@pytest.fixture
def sample_context():
    return {
        "patient_id": "p_test_001",
        "active_items": [{"service_name": "Botox", "price": 800.0, "status": "quoted"}],
        "behavioral_profile": {"communication_style": "friendly"}
    }

# From optimize_gatekeeper.py — convert case to DSPy Example
def make_example(case: dict) -> dspy.Example:
    """Converte um test case dict para dspy.Example."""
    return dspy.Example(
        clinic_name=case["clinic_name"],
        sdr_name=case.get("sdr_name", "Vera"),
        conversation_history=case.get("conversation_history", []),
        latest_message=case.get("latest_message"),
        current_hour=case.get("current_hour", 10),
        current_weekday=case.get("current_weekday", 1),
        expected_stage=case["expected_stage"],
    ).with_inputs(
        "clinic_name", "sdr_name", "conversation_history",
        "latest_message", "current_hour", "current_weekday",
    )
```

**Location:**
- Test cases: `app/agents/sdr/test_gatekeeper_cases.json` (49 cases: 41 synthetic + 8 real)
- Conversion utilities: `app/agents/sdr/optimize_gatekeeper.py` has `make_example()`
- No factory pattern; cases are raw dicts loaded from JSON

## Coverage

**Requirements:** No explicit coverage target enforced; "good coverage" is implicit

**View Coverage:**
```bash
# No standard command; would require pytest-cov or coverage.py
# Alternative: analyze test logs manually
python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases > results.txt
grep "✅ PASS\|❌ FAIL" results.txt | wc -l
```

**Current Status:**
- Gatekeeper: 49/49 cases passing (100% gate rate)
- Benchmark: Haiku (claude-haiku-4-5) achieves ~65% before optimization, improves to ~90%+ after BootstrapFewShot

## Test Types

**Unit Tests:**
- Scope: Individual agent outputs (GatekeeperAgent.forward(), PersonaDetector.forward())
- Approach: Given a conversation case, verify stage/response quality via judge LLM
- Location: `test_sdr_agents.py`, `test_ab_gatekeeper.py`
- Example: Test case with conversation history → run agent → judge output → pass/fail

**Integration Tests:**
- Scope: Full graph flow (detect_persona → route → process)
- Approach: Send request through FastAPI endpoint → verify output structure
- Location: `app/tests/test_router.py` (marked with `@pytest.mark.integration`)
- Example: HTTP POST to `/v1/gatekeeper` → validate GatekeeperResponse schema

**E2E Tests:**
- Framework: Not used in current codebase
- Would require: Supabase connection, Evolution API, n8n webhook triggers
- Current approach: Manual homolog testing via WhatsApp

## Common Patterns

**Async Testing:**
```python
# FastAPI tests would use async/await
async def test_gatekeeper_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/v1/gatekeeper", json=request_dict)
        assert response.status_code == 200
```

**Error Testing:**
```python
# From security middleware tests (implicit in code structure)
def test_api_key_validation(request_without_key):
    """Should return 401 if X-API-Key is missing or invalid."""
    # SecurityMiddleware checks for required_key
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"

def test_rate_limiting(many_rapid_requests):
    """Should return 429 after N requests per minute."""
    # SecurityMiddleware uses RateLimiter
    assert response.status_code == 429
```

**LLM Output Validation:**
```python
# From agent.py — handles LLM returning wrong types
def safe_str(val, default: str = "") -> str:
    """Safely convert any DSPy output field to string."""
    if val is None:
        return default
    if isinstance(val, str):
        return val
    return str(val)

# From agent.forward() — validate and promote stage
valid_stages = ["opening", "requesting", "handling_objection", "success", "failed"]
stage = safe_str(result.conversation_stage, "").lower().strip()
if stage not in valid_stages:
    print(f"⚠️  GatekeeperAgent: stage inválido recebido do LLM: '{stage}'")

# Auto-promote to success if contact extracted
if extracted_contact and stage not in ["success", "failed"]:
    stage = "success"
```

**Judge-Based Evaluation:**

```python
# From test_sdr_agents.py — use GPT-4o as judge for strategy compliance
def judge_gatekeeper_response(scenario: dict, result: dict) -> dict:
    """Avalia se a resposta do agente está correta usando GPT-4o como juiz fixo."""
    verdict = _judge(
        strategy=_GATEKEEPER_STRATEGY.strip(),  # Full 162-line strategy document
        conversation=conv_text,                  # History formatted as "Iris: ...\nRecepção: ..."
        latest_message=str(latest),
        agent_response=result.get("response_message", ""),
        expected_stage=scenario.get("expected_stage", "?"),
        actual_stage=result.get("conversation_stage", "?"),
    )
    return {"valid": verdict.is_valid == "true", "reason": verdict.reason}
```

## Test Optimization (BootstrapFewShot)

**Framework:** DSPy BootstrapFewShot optimizer

**Pattern:**
```python
# From optimize_gatekeeper.py
optimizer = dspy.BootstrapFewShot(
    metric=stage_metric,                        # Metric function: stage match
    max_bootstraps=10,                          # Try 10 bootstrap iterations
    max_labeled_demos=N,                        # Max N few-shot examples
    max_rounds=3,
)

optimized_agent = optimizer.compile(
    student=GatekeeperAgent(load_optimized=False),  # Use base model
    trainset=train_examples,                        # Convert JSON cases to dspy.Examples
    valset=val_examples,                            # Validate gate
)

optimized_agent.save(ARTIFACT_PATH)             # Save to artifacts/gatekeeper_optimized.json
```

**Metric:**
```python
def stage_metric(example, pred, trace=None) -> bool:
    """Métrica primária: stage classificado corretamente."""
    actual = pred.get("conversation_stage", "")
    return actual == example.expected_stage
```

**Gate:** 90% of cases must pass validation before artifact is saved

**Artifact Loading:** Automatic in `GatekeeperAgent.__init__()` if `load_optimized=True` and artifact exists

---

*Testing analysis: 2025-03-17*
