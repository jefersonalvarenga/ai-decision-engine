# Codebase Concerns

**Analysis Date:** 2025-03-17

## Tech Debt

### Missing Enrichment Data Pipeline
- **Issue:** Enrichment fields (`google_rating`, `google_reviews`, `google_ads_count`) exist in Supabase `gk_leads` table but are never transmitted to FastAPI in the n8n payload
- **Files:** `app/agents/sdr/gatekeeper/signature.py`, n8n workflow (external)
- **Impact:** GatekeeperAgent cannot use recovery tactics that require social proof (e.g., "4.9 com 700 avaliações" in Graciosa pattern). Agent is theoretically capable but data pipeline is incomplete.
- **Fix approach:**
  1. Add enrichment fields to n8n `Merge - Contexto da Conversa` node
  2. Extend `GatekeeperInput` pydantic model to include `google_rating`, `google_reviews`, `google_ads_count`
  3. Pass enrichment data to agent signature as context
  4. Update agent to conditionally use `data_hook` tactic when enrichment is available

### Outdated Prompt/Strategy Mismatch
- **Issue:** `signature.py` line 42 lists 5 tactics (`direct | feedback | referral | social_proof | data_hook`) but signature uses different names: `ltv_hook | leak_fix | social_proof | data_hook` (line 83-93). Also signature says "5 táticas" when there are actually 4 unique ones in the code.
- **Files:** `app/agents/sdr/gatekeeper/signature.py` (lines 42, 83-93)
- **Impact:** Documentation inconsistency, potential confusion during optimization or agent tuning. Minor — agent behavior is correct, only naming is unclear.
- **Fix approach:** Update line 42 to list actual tactics: `ltv_hook | leak_fix | social_proof | data_hook` and remove references to unused tactics

### Pitch Content Not Updated
- **Issue:** Current pitch references "recuperar em torno de R$5 mil por mês em pacientes inativos" (line 195 CLAUDE.md) but desired pitch is "Ajudamos clínicas a converter mais os leads que já chegam pelos anúncios". Signature still uses old pitch language.
- **Files:** `app/agents/sdr/gatekeeper/signature.py` (implicit, via LLM prompt), CLAUDE.md line 195
- **Impact:** Agent messaging doesn't reflect current business positioning. Lower conversion potential for new leads.
- **Fix approach:** Update prompt language in signature to reference lead conversion from paid ads instead of patient reactivation

---

## Known Bugs

### Artifact-Induced Regression (Documented but Unresolved)
- **Symptoms:** Running `optimize_gatekeeper.py` can generate `artifacts/gatekeeper_optimized.json` that causes performance drop from 100% to 51%
- **Files:** `app/agents/sdr/optimize_gatekeeper.py`, `app/agents/sdr/gatekeeper/agent.py` (lines 31-37)
- **Trigger:**
  1. Run `python -m app.agents.sdr.optimize_gatekeeper`
  2. BootstrapFewShot selects demos with empty `rationale` fields
  3. Demos have poor distribution (missing key patterns)
  4. GatekeeperAgent loads artifact and performance drops
- **Workaround:** Delete `artifacts/gatekeeper_optimized.json` to restore baseline behavior. Do not run optimizer without validating output.
- **Root cause:** BootstrapFewShot optimizer may select demos that lack sufficient reasoning context, degrading agent quality. Validator may not be catching this edge case.

### Gender Pronoun Inconsistency (Partially Fixed)
- **Symptoms:** Agent occasionally uses masculine pronouns ("Obrigado" instead of "Obrigada") despite signature explicitly requiring feminine pronouns
- **Files:** `app/agents/sdr/gatekeeper/signature.py` (lines 10-11)
- **Trigger:** LLM doesn't always enforce gender consistency across response generation
- **Current mitigation:** Signature includes explicit instruction: "Sempre se refira a si mesma no feminino (ex: 'estou', 'sou eu', nunca 'fui eu o responsável')". Deployed as-is, monitoring in production.
- **Workaround:** None currently; relies on LLM consistency which is probabilistic

---

## Security Considerations

### Environment Variable Override Mechanism
- **Risk:** `config.py` uses `override=False` for dotenv loading, but EasyPanel environment variables always take precedence. If EasyPanel database is compromised or misconfigured, production can be hijacked without re-deployment.
- **Files:** `app/core/config.py` (lines 14, 53)
- **Current mitigation:** EasyPanel is internal infrastructure; access control depends on EasyScale's platform security
- **Recommendations:**
  1. Add logging to `init_dspy()` to record LLM provider/model at startup
  2. Validate that `DSPY_PROVIDER` and `DSPY_MODEL` are expected values before initializing
  3. Consider circuit breaker: if provider changes unexpectedly, fallback to safe default or fail loudly

### API Keys in Logs
- **Risk:** DSPy LM initialization (line 120 in config.py) prints model name, not API key, which is safe. However, if debug logging is ever enabled in DSPy, raw API keys could leak.
- **Files:** `app/core/config.py` (lines 86-122)
- **Current mitigation:** No debug logging enabled; print statements are minimal
- **Recommendations:**
  1. Ensure DSPy debug mode is never enabled in production
  2. Add log sanitization if DSPy logging is ever needed

---

## Performance Bottlenecks

### LLM Call Latency in Graph Nodes
- **Problem:** `detect_persona` runs on EVERY inbound message (no caching), even for ongoing conversations where persona is stable
- **Files:** `app/agents/sdr/gatekeeper/graph.py` (lines 30-57)
- **Cause:** Comment says "Roda sempre — sem cache, sem depender do detected_persona do Supabase" to enforce fresh classification. Trade-off: accuracy vs latency.
- **Current capacity:** Single LLM call ~0.5-1.5s per message; acceptable for WhatsApp flows
- **Improvement path:**
  1. Cache persona for 10 messages if confidence is "high"
  2. Or accept persona from n8n if provided and confidence > 0.8
  3. Re-classify only if pattern breaks (e.g., tone shift detected)

### Persona Detector Without Streaming
- **Problem:** PersonaDetector invokes LLM for classification on every inbound, no result caching
- **Files:** `app/agents/sdr/gatekeeper/persona_detector.py`, `app/agents/sdr/gatekeeper/graph.py` (lines 43-47)
- **Cause:** Design choice to re-classify to catch persona changes (e.g., receptionist hands off to manager)
- **Scaling concern:** At 100 conversations/minute, this is 100+ LLM calls/minute just for persona detection
- **Improvement path:**
  1. Implement soft cache: accept `detected_persona` from n8n input if provided
  2. Only re-detect if flag `force_detect=True` or if message has anomalous pattern
  3. Store confidence level; only re-detect if confidence < 0.7

---

## Fragile Areas

### GatekeeperAgent Output Validation (Defensive Coding)
- **Files:** `app/agents/sdr/gatekeeper/agent.py` (lines 39-110)
- **Why fragile:**
  - Lines 84-87: Invalid stage from LLM is logged as warning but not rejected; malformed stage passes through
  - Lines 92-95: Contact extraction triggers automatic stage promotion to "success" even if LLM returned different stage
  - Lines 97-99: If `response_message` is "null" string (not Python None), it's treated as empty
- **Safe modification:**
  1. Validate stage is in `["opening", "requesting", "handling_objection", "success", "failed"]` before using
  2. Don't auto-promote stage; trust LLM stage decision or fail validation if inconsistency detected
  3. Add unit tests for edge cases: malformed phone, "null" string responses, stage mismatches
- **Test coverage:**
  - `test_sdr_agents.py` runs 49 test cases but does not test invalid LLM outputs or type mismatches
  - No tests for `safe_str()` utility function
  - No tests for stage validation logic

### Menu Bot Detection Hard-Coded Rule
- **Files:** `app/agents/sdr/gatekeeper/persona_detector.py` (lines 95-98)
- **Why fragile:**
  - Lines 95-98 have priority rule: if message contains "escolha uma opção" or "selecione uma opção", immediately classify as `menu_bot` without further analysis
  - This is exact substring matching; variations like "escolha uma das opções" or "selecione abaixo" are handled but Portuguese text variations could slip through
  - Language-agnostic clinics (English menus) won't match and will be misclassified
- **Safe modification:**
  1. Use fuzzy matching or tokenization instead of exact strings
  2. Add pattern for multi-language menu detection (e.g., numbered lists with consistent structure)
  3. Test against international clinic data if expanding to non-Portuguese markets
- **Test coverage:** PersonaDetector has test cases in `test_gatekeeper_cases.json` but coverage for edge cases like Portuguese variant menus is unclear

### Attempt Count Not Passed to GatekeeperAgent
- **Files:** `app/agents/sdr/optimize_gatekeeper.py` (lines 81-99), `app/agents/sdr/gatekeeper/signature.py` signature doesn't include `attempt_count` input
- **Why fragile:**
  - Optimizer uses `attempt_count` when creating dspy.Example (line 93)
  - But GatekeeperAgent.forward() does not accept `attempt_count` parameter (line 59-67)
  - Agent can't enforce "give up after 3 handling_objection" rule because it doesn't know the attempt number
  - Signature contains rules about 3rd attempt progression (lines 104-117) but no way to count attempts within a single request
- **Safe modification:**
  1. Add `attempt_count` to signature inputs
  2. Pass `attempt_count` from graph state to agent
  3. Update tests to verify progression works correctly
- **Test coverage:** Cases in JSON do not seem to set `attempt_count_override` field; unclear if this is tested

---

## Scaling Limits

### Single Artifact File for Few-Shot Demos
- **Current capacity:** `artifacts/gatekeeper_optimized.json` is ~28KB (from Bash output); contains all few-shot demos
- **Limit:** As demos grow (more cases added to `test_gatekeeper_cases.json`), artifact grows linearly. At ~6 demos per KB, artifact could reach several hundred KB.
- **Scaling path:**
  1. Implement versioned artifacts: `gatekeeper_optimized_v1.json`, `gatekeeper_optimized_v2.json`
  2. Or implement artifact caching: pre-load into memory at startup, don't load on every request
  3. Consider pruning: keep only top N demos by validation score

### Concurrent LLM Request Throttling
- **Problem:** No rate limiting or request queuing in agent code. All requests go directly to LLM provider.
- **Files:** `app/agents/sdr/gatekeeper/agent.py`, `app/agents/sdr/gatekeeper/graph.py`
- **Current capacity:** Depends on LLM provider (Claude, OpenAI, Groq). No internal backpressure mechanism.
- **Scaling path:**
  1. Add request queue with max concurrency limit
  2. Implement retry logic with exponential backoff for rate limits
  3. Add circuit breaker if LLM provider returns 429 (too many requests)

---

## Dependencies at Risk

### DSPy Version Lock (2.5.43)
- **Risk:** `requirements.txt` pins `dspy-ai==2.5.43`. DSPy is actively developed; 2.5.43 may be 2-3 versions behind stable.
- **Impact:** Missing bug fixes, missing new LLM provider support, missing API improvements
- **Migration plan:**
  1. Test against latest DSPy (check for breaking changes in ChainOfThought, Signatures)
  2. Update to `dspy-ai>=2.5.43,<3.0` if no breaking changes
  3. Monitor DSPy changelog quarterly

### LangGraph Version (0.2.60)
- **Risk:** LangGraph is still in active development (0.2.x); breaking changes may occur in 0.3.x or 1.0
- **Impact:** Graph nodes may need refactoring if LangGraph API changes
- **Migration plan:**
  1. Pin to `langgraph>=0.2.60,<1.0`
  2. Subscribe to LangGraph releases
  3. Allocate time for migration when 1.0 is released

### Anthropic Client Version (0.40.0)
- **Risk:** Anthropic API evolves; 0.40.0 may be outdated if using new Claude models
- **Impact:** May not support claude-opus-4, claude-4-turbo, or future models
- **Migration plan:** Update to latest `anthropic>=1.0.0` when available; test against production workload

---

## Missing Critical Features

### No Audit Trail for Agent Decisions
- **Problem:** `gk_logs` table stores reasoning, but no structured audit trail for multi-step decisions (e.g., why persona was detected as X, why stage transitioned from Y to Z)
- **Blocks:** Post-mortem debugging, root cause analysis for failed conversations, regulatory compliance (if required)
- **Fix approach:**
  1. Extend `gk_logs` with `decision_tree` jsonb field capturing intermediate decisions
  2. Add timestamps for each decision node

### No Manual Override/Approval Queue
- **Problem:** All agent responses are sent directly. No human-in-the-loop for sensitive cases (e.g., if agent proposes "failed" after 1 attempt).
- **Blocks:** Control of SDR voice, brand safety, compliance in regulated healthcare market
- **CLAUDE.md mentions:** "Approval queue no n8n: SDR gera → Telegram notifica → Jeferson aprova/edita → envia" (line 215) — not yet implemented
- **Fix approach:**
  1. Implement n8n approval workflow with Telegram notification
  2. Store pending messages in `gk_pending_messages` table
  3. Add HTTP endpoint to approve/reject/edit before sending

### No Rollback Strategy for Optimized Artifacts
- **Problem:** If `gatekeeper_optimized.json` causes regression (as known bug), only recovery is deletion. No version history, no A/B switch.
- **Blocks:** Quick recovery if bad artifact is deployed to production
- **Fix approach:**
  1. Store artifacts with timestamps: `gatekeeper_optimized_20250317_143000.json`
  2. Add config flag `GATEKEEPER_ARTIFACT_VERSION` to choose which artifact to load
  3. Or implement A/B flag: `GATEKEEPER_USE_OPTIMIZED=true/false`

---

## Test Coverage Gaps

### No Type Validation Tests for DSPy Outputs
- **Untested area:** LLM sometimes returns non-string types for string fields (noted in `utils.py` line 9). No test verifies that `safe_str()` handles all edge cases (None, int, list, dict, custom objects).
- **Files:** `app/agents/sdr/gatekeeper/utils.py` (lines 6-16), `app/agents/sdr/gatekeeper/agent.py` (lines 79-81)
- **Risk:** If LLM returns unexpected type, `safe_str()` falls back to `str(val)` which may produce "None" or "[object Object]" in response
- **Priority:** Medium — guards against silent failures

### No Edge Case Tests for Persona Detection
- **Untested area:** Menu detection with non-Portuguese variations, multi-language menus, ambiguous messages near decision boundaries
- **Files:** `test_gatekeeper_cases.json` — no documented coverage of these cases
- **Risk:** Persona misclassification → wrong agent behavior
- **Priority:** Medium — affects international expansion

### No Error Recovery Tests
- **Untested area:** What happens if LLM request fails mid-conversation? What if DSPy raises exception? How does graph handle it?
- **Files:** `app/agents/sdr/gatekeeper/graph.py` (lines 90-117) — no try/except around `gatekeeper_agent.forward()`
- **Risk:** Unhandled exception crashes request; n8n gets no response; conversation stalls
- **Priority:** High — affects production reliability

### No Load/Stress Tests
- **Untested area:** How does agent perform with 100+ concurrent conversations? With conversation history > 50 messages?
- **Files:** No load test scripts found in codebase
- **Risk:** Performance degradation or OOM errors in production not caught until customer impact
- **Priority:** High — critical for production scalability

### No A/B Test Infrastructure
- **Untested area:** No framework for safely comparing two agents (e.g., Gatekeeper v1 vs v2) in production
- **Files:** `test_ab_gatekeeper.py` exists but is offline validation, not production A/B
- **Risk:** Can't safely roll out improvements; must do all/nothing deployment
- **Priority:** Medium — affects continuous improvement velocity

---

## Data Quality Concerns

### Conversation History Format Ambiguity
- **Issue:** Conversation history is passed as list of `ConversationTurn` (role: "agent" | "human") but signature documentation uses different terminology: "recepcionista", "Vera", etc.
- **Files:** `app/agents/sdr/state.py` (lines 21-24), `app/agents/sdr/gatekeeper/signature.py` (line 183)
- **Impact:** Agent may confuse which messages are from agent vs reception if role is not clear in prompt
- **Fix approach:** Add clarification in signature: "agent = Vera (sua resposta anterior), human = recepcionista (resposta da clínica)"

### No Validation for Extracted Contact Format
- **Issue:** `_clean_phone()` accepts any string with 10+ digits after removing non-digits. No validation that it looks like a valid Brazilian phone number (e.g., area code 11-99, number format XXXXX-XXXX).
- **Files:** `app/agents/sdr/gatekeeper/agent.py` (lines 39-43)
- **Impact:** Agent may extract malformed numbers (e.g., date strings "2301" + "1990" = "23011990", which passes validation)
- **Fix approach:** Add phone format validation: must match pattern `^[1-9][0-9]{10,11}$` (Brazilian mobile: 11 digits starting with 1-9)

---

## Operational Concerns

### No Metrics/Observability
- **Issue:** `gk_logs` table exists but no dashboard/alert system to monitor agent health. Unknown if agent is degrading in production.
- **Files:** `app/agents/sdr/gatekeeper/graph.py` — logs printed to stdout, fire-and-forget via httpx to Supabase
- **Impact:** Production issues may go unnoticed for days
- **Fix approach:**
  1. Implement metrics collection: success rate per clinic, latency per request, error rate
  2. Set up alerts if success rate drops below 80% in 1-hour window
  3. Add Datadog/CloudWatch integration if using cloud provider

### No Graceful Degradation
- **Issue:** If LLM provider is down, agent fails hard. No fallback to rule-based response or queued retry.
- **Files:** `app/agents/sdr/gatekeeper/agent.py` (line 69-77) — no try/except around LLM call
- **Impact:** 100% failure rate if LLM unavailable; n8n workflow stalls
- **Fix approach:**
  1. Wrap LLM calls in try/except
  2. Return safe default response (e.g., "Um momento...") if LLM fails
  3. Implement request retry queue to Supabase for manual processing

---

*Concerns audit: 2025-03-17*
