# EasyScale - Guia de Início Rápido ⚡

**Tempo estimado:** 10 minutos

Este guia te leva do zero ao primeiro teste do Router Agent em menos de 10 minutos.

## ✅ Pré-requisitos

- Python 3.10+ instalado
- API key de algum provider (OpenAI, Anthropic, ou Groq)
- Terminal/Command Prompt

## 🚀 Setup em 5 Passos

### 1️⃣ Clone e Instale (2 min)

```bash
# Clone o repositório
git clone <seu-repo>
cd easyscale

# Crie ambiente virtual
python -m venv venv

# Ative (Linux/Mac)
source venv/bin/activate

# Ative (Windows)
venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt
```

### 2️⃣ Configure Variáveis de Ambiente (2 min)

```bash
# Copie o template
cp .env.example .env

# Edite o .env
nano .env  # ou use seu editor favorito
```

**Mínimo necessário** (escolha um provider):

```bash
# Opção 1: OpenAI (Recomendado para começar)
DSPY_PROVIDER=openai
DSPY_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-proj-...

# Opção 2: Anthropic
DSPY_PROVIDER=anthropic
DSPY_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-...

# Opção 3: Groq (Gratuito!)
DSPY_PROVIDER=groq
DSPY_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_...

# Supabase (pode pular por enquanto para testes locais)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJ...
```

**Não tem API key?** Pegue uma grátis:
- OpenAI: https://platform.openai.com/api-keys
- Groq: https://console.groq.com/keys (100% gratuito!)
- Anthropic: https://console.anthropic.com/

### 3️⃣ Teste Básico (2 min)

```bash
# Rode o exemplo básico
python router_agent.py
```

**Saída esperada:**
```
=== Example 1: Sales Inquiry ===
Intents: ['SALES']
Urgency: 2
Reasoning: Customer asking about pricing and payment options...
Response: [CLOSER AGENT] Processing sales inquiry...

=== Example 2: Scheduling ===
Intents: ['SCHEDULING']
Urgency: 3
Reasoning: Patient wants to book appointment...
Response: [SCHEDULER AGENT] Processing appointment request...

=== Example 3: Medical Urgency ===
Intents: ['MEDICAL_ASSESSMENT']
Urgency: 4
Reasoning: Patient reports allergic reaction and swelling...
Response: [MEDICAL AGENT] Assessing medical concern...
```

✅ **Se você viu isso, o Router está funcionando!**

### 4️⃣ Teste Interativo via API (2 min)

```bash
# Inicie o servidor FastAPI
uvicorn api:app --reload
```

Abra o navegador em: **http://localhost:8000/docs**

Você verá o Swagger UI interativo. Clique em **POST /api/v1/test/classify** e teste:

```json
{
  "message": "quanto custa o botox?"
}
```

Clique em **Execute**. Você deve ver:

```json
{
  "message": "quanto custa o botox?",
  "intents": ["SALES"],
  "urgency": 2,
  "reasoning": "Customer asking about pricing..."
}
```

### 5️⃣ Teste Outros Exemplos (2 min)

Experimente diferentes mensagens PT-BR:

**Vendas:**
```
"tá muito caro, tem desconto?"
"posso parcelar em quantas vezes?"
"qual o valor da promoção?"
```

**Agendamento:**
```
"quero marcar para amanhã"
"tem horário de tarde?"
"preciso remarcar minha consulta"
```

**Urgência Médica:**
```
"estou com muita dor"
"fiquei com alergia"
"está muito inchado e vermelho"
```

**FAQ:**
```
"como funciona o botox?"
"quanto tempo dura o resultado?"
"precisa de anestesia?"
```

## 🎯 Exemplos Práticos de Uso

### Exemplo 1: Testar via Python Direto

```python
from router_agent import build_easyscale_graph, configure_dspy
import os

# Configure
configure_dspy(
    provider="openai",
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY")
)

# Build graph
graph = build_easyscale_graph()

# Teste
result = graph.invoke({
    "context": {
        "patient_id": "test_001",
        "active_items": [{"service_name": "Botox", "price": 800}],
        "behavioral_profile": {"price_sensitivity": "high"}
    },
    "latest_message": "tá caro demais",
    "intent_queue": [],
    "final_response": "",
    "urgency_score": 0,
    "reasoning": ""
})

print(f"🎯 Intenções: {result['intent_queue']}")
print(f"⚡ Urgência: {result['urgency_score']}/5")
print(f"💭 Raciocínio: {result['reasoning']}")
```

### Exemplo 2: Testar via cURL

```bash
# Health check
curl http://localhost:8000/health

# Classificação rápida
curl -X POST "http://localhost:8000/api/v1/test/classify?message=quanto%20custa"

# Request completo
curl -X POST "http://localhost:8000/api/v1/router" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "patient_id": "p_12345",
      "active_items": [{"service_name": "Botox", "price": 800}],
      "behavioral_profile": {"communication_style": "direct"}
    },
    "message": "quero marcar para hoje"
  }'
```

### Exemplo 3: Testar via Postman/Insomnia

**Endpoint:** `POST http://localhost:8000/api/v1/router`

**Body (JSON):**
```json
{
  "context": {
    "patient_id": "p_test",
    "active_items": [
      {
        "service_name": "Limpeza de Pele",
        "price": 250,
        "status": "quoted"
      }
    ],
    "behavioral_profile": {
      "communication_style": "friendly",
      "price_sensitivity": "medium"
    },
    "conversation_history": []
  },
  "message": "oi, tenho interesse mas tá caro"
}
```

**Response:**
```json
{
  "intents": ["SALES"],
  "urgency_score": 2,
  "reasoning": "Customer expressing interest but has price concern...",
  "routed_to": "closer_agent",
  "response": "[CLOSER AGENT] Processing sales inquiry...",
  "processing_time_ms": 843.2
}
```

## 🧪 Rode os Testes

```bash
# Todos os testes
pytest test_router.py -v

# Somente testes rápidos (sem integration)
pytest test_router.py -v -m "not integration"

# Com output detalhado
pytest test_router.py -v -s

# Com coverage
pytest test_router.py --cov=router_agent
```

**Saída esperada:**
```
test_router.py::TestIntentClassification::test_sales_intent_basic PASSED
test_router.py::TestIntentClassification::test_scheduling_intent_basic PASSED
test_router.py::TestRoutingLogic::test_medical_priority PASSED
...

==================== 15 passed in 2.3s ====================
```

## 🔍 Troubleshooting

### Erro: "No module named 'dspy'"

```bash
# Reinstale as dependências
pip install -r requirements.txt --force-reinstall
```

### Erro: "API key not found"

```bash
# Verifique se o .env está correto
cat .env | grep API_KEY

# Ou exporte manualmente
export OPENAI_API_KEY="sk-..."
```

### Erro: "Connection to Supabase failed"

Não se preocupe! Para testes iniciais, você não precisa do Supabase. Use os exemplos com contexto mock.

Se quiser testar com Supabase, veja [DEPLOYMENT.md](DEPLOYMENT.md#setup-do-banco-supabase).

### Erro: "Port 8000 already in use"

```bash
# Use outra porta
uvicorn api:app --reload --port 8001

# Ou mate o processo na porta 8000
# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Latência muito alta (>5s)

```bash
# Use um modelo mais rápido
DSPY_MODEL=gpt-4o-mini  # Mais rápido que gpt-4
# ou
DSPY_PROVIDER=groq      # Ultra-rápido (Llama via Groq)
```

## 📚 Próximos Passos

Agora que você testou o básico, explore:

1. **[README.md](README.md)** - Visão completa do sistema
2. **[architecture_diagram.md](architecture_diagram.md)** - Entenda a arquitetura
3. **[ADVANCED_USAGE.md](ADVANCED_USAGE.md)** - Customizações avançadas
4. **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deploy em produção

### Customize para seu caso de uso:

**Adicionar nova intenção:**
```python
# router_agent.py
class IntentType(str, Enum):
    # ... existing
    COMPLAINT = "COMPLAINT"  # Nova intenção

# Atualize RouterSignature com novos indicadores PT-BR
```

**Ajustar prioridades:**
```python
# router_agent.py
def should_continue(state: AgentState):
    # Mude a ordem de priorização aqui
    if "COMPLAINT" in intent_queue:
        return "complaint_agent"  # Maior prioridade
    if "MEDICAL_ASSESSMENT" in intent_queue:
        return "medical_agent"
    # ...
```

**Trocar modelo LLM:**
```bash
# .env
DSPY_PROVIDER=anthropic
DSPY_MODEL=claude-3-5-sonnet-20241022

# Restart servidor - done!
```

## 💡 Dicas Finais

✅ **Para desenvolvimento:**
- Use `gpt-4o-mini` (barato e rápido)
- Mantenha `DEBUG_MODE=true` no `.env`
- Use `uvicorn api:app --reload` para hot reload

✅ **Para testes:**
- Rode `pytest` antes de cada commit
- Use `pytest --cov` para verificar coverage
- Adicione novos testes para customizações

✅ **Para produção:**
- Use modelos maiores (`gpt-4`, `claude-3.5-sonnet`)
- Configure `DEBUG_MODE=false`
- Implemente rate limiting e autenticação
- Monitore com Sentry + LangSmith

## 🎉 Pronto!

Você agora tem o EasyScale Router rodando localmente!

**Perguntas?**
- 📖 Leia a [documentação completa](README.md)
- 🐛 [Abra uma issue](seu-repo/issues)
- 💬 [Entre em contato](seu-email)

---

**Tempo total:** ~10 minutos ⚡
**Última atualização:** 2026-01-20
