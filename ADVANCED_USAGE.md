# EasyScale - Guia de Uso Avançado

Este documento cobre cenários avançados, edge cases, e customizações do sistema EasyScale.

## 🎯 Cenários de Uso Avançado

### 1. Multi-Intent Messages (Mensagens com Múltiplas Intenções)

O sistema suporta detecção de múltiplas intenções em uma única mensagem:

```python
# Exemplo: Urgência + Agendamento
message = "estou com alergia no local, preciso remarcar minha próxima sessão"

# DSPy Output:
# intents = ["MEDICAL_ASSESSMENT", "SCHEDULING"]
# urgency_score = 4

# Roteamento: MEDICAL_ASSESSMENT tem prioridade
# → Routes to medical_agent
# → SCHEDULING fica na fila para processar depois
```

**Customização: Sequential Intent Processing**

Para processar múltiplas intenções sequencialmente:

```python
from router_agent import build_easyscale_graph

def build_multi_intent_graph():
    """Graph que processa todas as intenções na fila."""
    workflow = StateGraph(AgentState)

    # Add nodes...
    workflow.add_node("router", router_node)
    workflow.add_node("medical_agent", medical_agent_node)
    workflow.add_node("scheduler_agent", scheduler_agent_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional edges
    workflow.add_conditional_edges("router", should_continue, {...})

    # KEY: Agents loop back to router to process next intent
    workflow.add_edge("medical_agent", "router")  # ← Loop back!
    workflow.add_edge("scheduler_agent", "router")

    return workflow.compile()

# Uso:
graph = build_multi_intent_graph()
result = graph.invoke({
    "context": {...},
    "latest_message": "estou com alergia e preciso remarcar",
    "intent_queue": [],
    ...
})

# Processamento:
# 1. Router → MEDICAL_ASSESSMENT, SCHEDULING
# 2. Medical Agent processa → Remove MEDICAL_ASSESSMENT da fila
# 3. Loop back to Router
# 4. Router → SCHEDULING ainda na fila
# 5. Scheduler Agent processa → Fila vazia
# 6. END
```

### 2. Context-Aware Intent Detection

Use o contexto do paciente para melhorar a classificação:

```python
class EnhancedRouterSignature(dspy.Signature):
    """Enhanced signature que considera histórico."""

    context_json: str = dspy.InputField(...)
    patient_message: str = dspy.InputField(...)

    # NEW: Contextualize based on conversation state
    conversation_state: str = dspy.InputField(
        desc=(
            "Current state of the conversation:\n"
            "- 'initial_contact': First message from patient\n"
            "- 'negotiating': Discussing pricing/terms\n"
            "- 'scheduling': In process of booking\n"
            "- 'post_procedure': After treatment\n"
            "- 'follow_up': Scheduled follow-up conversation"
        )
    )

    intents: List[str] = dspy.OutputField(...)
    urgency_score: int = dspy.OutputField(...)
    reasoning: str = dspy.OutputField(...)

# Exemplo:
# Se conversation_state = "post_procedure" e message = "está doendo"
# → Automaticamente eleva urgency_score
# → Prioriza MEDICAL_ASSESSMENT
```

### 3. Dynamic Prompt Adaptation (Adaptação de Prompt)

Ajuste o comportamento do router baseado em perfil comportamental:

```python
def get_adapted_system_prompt(behavioral_profile: dict) -> str:
    """Adapta instruções baseado no perfil do paciente."""

    base_prompt = "You are an intent classifier..."

    # High price sensitivity → Detect price objections mais agressivamente
    if behavioral_profile.get("price_sensitivity") == "high":
        base_prompt += """
        IMPORTANT: This patient is price-sensitive. Pay extra attention to:
        - Subtle price objections ('um pouco caro', 'vou pensar')
        - Requests for discounts or payment plans
        - Comparison shopping signals
        Classify as SALES even for implicit pricing concerns.
        """

    # Fast decision speed → Detect urgency to book
    if behavioral_profile.get("decision_speed") == "fast":
        base_prompt += """
        This patient makes quick decisions. Watch for:
        - Immediate booking intent ('hoje mesmo', 'o mais rápido possível')
        - Readiness to commit signals
        Elevate urgency_score for scheduling intents.
        """

    return base_prompt

# Uso: Inject into DSPy signature
# (Requer customização do DSPy module)
```

### 4. Urgency Escalation Rules

Implemente regras adicionais de escalação:

```python
def calculate_adjusted_urgency(
    base_urgency: int,
    context: dict,
    message: str
) -> int:
    """Ajusta urgency score baseado em regras de negócio."""

    adjusted = base_urgency

    # Rule 1: Post-procedure dentro de 72h → +1 urgency
    if context.get("hours_since_procedure", float('inf')) < 72:
        if any(word in message.lower() for word in ["dor", "inchado", "vermelho"]):
            adjusted += 1

    # Rule 2: Pregnant patients → +2 urgency for any health concern
    if context.get("patient_demographics", {}).get("pregnant"):
        if "MEDICAL_ASSESSMENT" in context.get("intent_queue", []):
            adjusted += 2

    # Rule 3: VIP clients → +1 urgency (faster response time)
    if context.get("client_tier") == "vip":
        adjusted += 1

    # Cap at 5
    return min(adjusted, 5)

# Uso:
def enhanced_router_node(state: AgentState) -> AgentState:
    """Router node com urgency adjustment."""

    # Classificação base
    result = router_node(state)

    # Ajuste de urgência
    result["urgency_score"] = calculate_adjusted_urgency(
        base_urgency=result["urgency_score"],
        context=state["context"],
        message=state["latest_message"]
    )

    return result
```

## 🧪 Edge Cases e Handling

### Case 1: Mensagens Ambíguas

```python
# Mensagem: "oi"
# Problema: Muito genérica, nenhuma intenção clara

# Solução 1: Fallback para GENERAL_INFO
def should_continue(state: AgentState):
    intent_queue = state.get("intent_queue", [])

    if not intent_queue:
        # Se mensagem muito curta, rota para general agent
        if len(state["latest_message"].strip()) < 10:
            return "general_agent"
        return "__end__"
    # ... resto da lógica

# Solução 2: Proactive Clarification
class ClarificationAgent:
    def handle(self, state: AgentState) -> AgentState:
        """Agent que pede clarificação."""
        return {
            "final_response": (
                "Olá! Fico feliz em te ajudar. "
                "Você gostaria de:\n"
                "1. Saber sobre preços e serviços\n"
                "2. Agendar uma consulta\n"
                "3. Tirar dúvidas sobre procedimentos\n"
                "4. Falar sobre um procedimento que já fez"
            )
        }
```

### Case 2: Spam e Mensagens Irrelevantes

```python
# Mensagem: "Olá, temos uma oportunidade de negócio para você!"
# Problema: Spam, não é paciente legítimo

# Solução: Spam Detection Layer
class SpamDetector(dspy.Signature):
    message: str = dspy.InputField()
    is_spam: bool = dspy.OutputField(
        desc="True if message is spam, solicitation, or irrelevant"
    )
    confidence: float = dspy.OutputField()

def spam_filter_node(state: AgentState) -> AgentState:
    """Pre-router spam filtering."""
    detector = dspy.ChainOfThought(SpamDetector)

    result = detector(message=state["latest_message"])

    if result.is_spam and result.confidence > 0.8:
        return {
            "intent_queue": [],
            "final_response": "",  # Ignora silenciosamente
            "reasoning": f"Spam detected: {result.confidence}"
        }

    return state

# Add to graph:
# workflow.add_node("spam_filter", spam_filter_node)
# workflow.set_entry_point("spam_filter")
# workflow.add_edge("spam_filter", "router")
```

### Case 3: Código-Switched Messages (PT-BR + EN)

```python
# Mensagem: "quero fazer um appointment para o botox"
# Problema: Mistura de português e inglês

# DSPy já lida bem com isso se instruído corretamente:
RouterSignature instruction:
  "The patient may mix Portuguese and English (code-switching).
   Examples: 'quero fazer um appointment' = 'quero marcar'
   Treat these as valid PT-BR messages and classify normally."
```

### Case 4: Emoji e Pontuação Excessiva

```python
# Mensagem: "URGENTE!!!! 😭😭😭 estou com MUITA DOR 😢😢"

# Problema: Emojis podem confundir o modelo

# Solução: Preprocessing
import re

def preprocess_message(message: str) -> str:
    """Clean message before classification."""

    # Remove emojis (keep text)
    message = re.sub(r'[^\w\s\u00C0-\u017F]', ' ', message)

    # Normalize multiple punctuation
    message = re.sub(r'!{2,}', '!', message)
    message = re.sub(r'\?{2,}', '?', message)

    # Lowercase for consistency
    message = message.lower().strip()

    return message

# Uso:
def router_node_with_preprocessing(state: AgentState) -> AgentState:
    cleaned_message = preprocess_message(state["latest_message"])

    return router_node({
        **state,
        "latest_message": cleaned_message
    })
```

## 🔧 Customizações Avançadas

### Custom Agent Implementation

Exemplo de implementação completa de um agente:

```python
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class AgentResponse:
    """Standardized agent response."""
    message: str
    next_action: str  # "wait_for_reply", "schedule_callback", "escalate"
    metadata: Dict[str, Any]

class CloserAgent:
    """Sales/closer agent implementation."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def handle(self, state: AgentState) -> AgentState:
        """Process sales inquiry."""

        context = state["context"]
        message = state["latest_message"]

        # 1. Detect price objection
        if self._is_price_objection(message):
            response = self._handle_price_objection(context, message)

        # 2. Detect interest in package
        elif self._is_package_interest(message):
            response = self._present_packages(context)

        # 3. General sales inquiry
        else:
            response = self._handle_general_inquiry(context, message)

        # Update conversation state in Supabase
        self._update_sales_stage(
            patient_id=context["patient_id"],
            stage=response.metadata.get("sales_stage")
        )

        return {
            "final_response": response.message,
            "intent_queue": [],  # Clear queue
        }

    def _is_price_objection(self, message: str) -> bool:
        """Detect price objection patterns."""
        objections = [
            "caro", "muito", "desconto", "barato",
            "não tenho", "acima do meu orçamento"
        ]
        return any(obj in message.lower() for obj in objections)

    def _handle_price_objection(
        self,
        context: dict,
        message: str
    ) -> AgentResponse:
        """Handle price objection with value reinforcement."""

        active_item = context["active_items"][0]
        price = active_item["price"]

        # Calculate value proposition
        value_props = [
            f"✨ Resultados duradouros de {self._get_duration(active_item)} meses",
            "👩‍⚕️ Realizado por profissionais especializados",
            "🏥 Clínica com certificação ANVISA",
        ]

        response = (
            f"Entendo sua preocupação com o investimento. "
            f"O valor de R$ {price:.2f} inclui:\n\n"
            + "\n".join(value_props) +
            f"\n\nPosso parcelar em até 3x sem juros no cartão. "
            f"Isso fica R$ {price/3:.2f} por mês. "
            f"Gostaria de saber mais sobre o que está incluso?"
        )

        return AgentResponse(
            message=response,
            next_action="wait_for_reply",
            metadata={"sales_stage": "handling_objection"}
        )

    # ... outros métodos
```

### Custom Conditional Routing

Roteamento baseado em regras de negócio complexas:

```python
def advanced_routing_logic(state: AgentState) -> str:
    """Advanced routing with business rules."""

    intent_queue = state["intent_queue"]
    context = state["context"]
    urgency = state["urgency_score"]

    # Rule 1: Critical medical + VIP → Direct to doctor
    if urgency >= 5 and context.get("client_tier") == "vip":
        return "doctor_direct_agent"

    # Rule 2: High-value lead (>5k) + sales intent → Senior closer
    total_quoted = sum(
        item["price"] for item in context.get("active_items", [])
    )
    if total_quoted > 5000 and "SALES" in intent_queue:
        return "senior_closer_agent"

    # Rule 3: After-hours → Leave voicemail + schedule callback
    from datetime import datetime
    now = datetime.now().hour
    if now < 8 or now > 20:  # Fora do horário comercial
        return "after_hours_agent"

    # Rule 4: Pregnant + any procedure question → Medical review
    if context.get("patient_demographics", {}).get("pregnant"):
        if "TECH_FAQ" in intent_queue:
            return "medical_review_agent"  # Requer aprovação médica

    # Default priority routing
    if "MEDICAL_ASSESSMENT" in intent_queue:
        return "medical_agent"
    if "SCHEDULING" in intent_queue:
        return "scheduler_agent"
    if "SALES" in intent_queue:
        return "closer_agent"

    return "__end__"
```

## 📊 Monitoring e Analytics

### Custom Metrics Collection

```python
from datetime import datetime
from typing import Optional

class RouterMetrics:
    """Collect metrics for analysis."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def log_routing_decision(
        self,
        patient_id: str,
        message: str,
        intents: list[str],
        urgency: int,
        routed_to: str,
        processing_time_ms: float,
        context: dict
    ):
        """Log routing decision for analytics."""

        self.supabase.from_("routing_metrics").insert({
            "patient_id": patient_id,
            "message_length": len(message),
            "intents": intents,
            "intent_count": len(intents),
            "urgency_score": urgency,
            "routed_to_agent": routed_to,
            "processing_time_ms": processing_time_ms,
            "patient_tier": context.get("client_tier"),
            "active_items_count": len(context.get("active_items", [])),
            "conversation_turn": len(context.get("conversation_history", [])),
            "timestamp": datetime.utcnow().isoformat()
        }).execute()

# Dashboard Queries:
"""
-- Intent distribution
SELECT intents, COUNT(*) as count
FROM routing_metrics
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY intents
ORDER BY count DESC;

-- Average urgency by time of day
SELECT EXTRACT(HOUR FROM timestamp) as hour,
       AVG(urgency_score) as avg_urgency
FROM routing_metrics
GROUP BY hour
ORDER BY hour;

-- Processing time percentiles
SELECT
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY processing_time_ms) as p50,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY processing_time_ms) as p95,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY processing_time_ms) as p99
FROM routing_metrics
WHERE timestamp > NOW() - INTERVAL '24 hours';
"""
```

## 🧠 Model Fine-Tuning

### DSPy Optimizer Usage

```python
from dspy.teleprompt import BootstrapFewShot

# 1. Prepare training data
training_examples = [
    dspy.Example(
        context_json='{"active_items": [...]}',
        patient_message="tá muito caro",
        intents=["SALES"],
        urgency_score=2
    ).with_inputs("context_json", "patient_message"),

    dspy.Example(
        context_json='{"active_items": [...]}',
        patient_message="estou com muita dor",
        intents=["MEDICAL_ASSESSMENT"],
        urgency_score=5
    ).with_inputs("context_json", "patient_message"),

    # ... mais exemplos
]

# 2. Define metric
def intent_accuracy(example, pred, trace=None):
    """Metric: intents match exactly."""
    return set(example.intents) == set(pred.intents)

# 3. Optimize
optimizer = BootstrapFewShot(metric=intent_accuracy)
optimized_router = optimizer.compile(
    RouterModule(),
    trainset=training_examples
)

# 4. Use optimized version
# optimized_router salva automaticamente few-shot examples
```

## 🔐 Security Best Practices

### Input Validation

```python
from pydantic import BaseModel, validator

class SafeRouterRequest(BaseModel):
    """Validated router request."""

    context: Dict[str, Any]
    message: str

    @validator("message")
    def message_must_be_reasonable(cls, v):
        """Prevent abuse."""
        if len(v) > 5000:
            raise ValueError("Message too long (max 5000 chars)")

        if len(v.strip()) == 0:
            raise ValueError("Message cannot be empty")

        return v

    @validator("context")
    def context_must_have_patient_id(cls, v):
        """Ensure patient ID exists."""
        if "patient_id" not in v:
            raise ValueError("Context must include patient_id")

        return v
```

### Rate Limiting per Patient

```python
from functools import lru_cache
from datetime import datetime, timedelta

class RateLimiter:
    """Per-patient rate limiting."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests: Dict[str, list[datetime]] = {}

    def is_allowed(self, patient_id: str) -> bool:
        """Check if request is allowed."""
        now = datetime.now()

        # Clean old requests
        if patient_id in self.requests:
            self.requests[patient_id] = [
                ts for ts in self.requests[patient_id]
                if now - ts < self.window
            ]

        # Check limit
        request_count = len(self.requests.get(patient_id, []))
        if request_count >= self.max_requests:
            return False

        # Record request
        if patient_id not in self.requests:
            self.requests[patient_id] = []
        self.requests[patient_id].append(now)

        return True

# Uso:
limiter = RateLimiter(max_requests=10, window_seconds=60)

@app.post("/api/v1/router")
async def route_message(request: RouterRequest):
    patient_id = request.context["patient_id"]

    if not limiter.is_allowed(patient_id):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait."
        )

    # ... process normally
```

---

**Última atualização:** 2026-01-20
**Mantenedor:** EasyScale Team
