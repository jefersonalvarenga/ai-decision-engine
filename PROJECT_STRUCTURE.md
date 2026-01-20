# EasyScale - Estrutura do Projeto

## 📁 Organização dos Arquivos

```
easyscale/
│
├── 📄 router_agent.py          # ⭐ CORE: Agente Router + LangGraph
│   ├── AgentState              # TypedDict com state do grafo
│   ├── RouterSignature         # DSPy signature para classificação
│   ├── RouterModule            # DSPy module (Chain of Thought)
│   ├── router_node()           # LangGraph node principal
│   ├── should_continue()       # Conditional routing logic
│   └── build_easyscale_graph() # Graph construction
│
├── 📄 config.py                # Configuração centralizada
│   ├── DSPyConfig              # Configuração do LLM
│   ├── SupabaseConfig          # Configuração do banco
│   ├── EasyScaleSettings       # Settings class (Pydantic)
│   └── get_settings()          # Singleton getter
│
├── 📄 api.py                   # FastAPI REST API
│   ├── POST /api/v1/router     # Endpoint principal de roteamento
│   ├── POST /api/v1/whatsapp/webhook  # Webhook WhatsApp
│   ├── POST /api/v1/test/classify     # Teste rápido
│   ├── GET /health             # Health check
│   └── Dependency injection    # Graph + Settings
│
├── 🧪 test_router.py           # Testes unitários e integração
│   ├── TestIntentClassification    # Testes de intent detection
│   ├── TestUrgencyScoring          # Testes de urgency score
│   ├── TestRoutingLogic            # Testes de routing
│   ├── TestGraphConstruction       # Testes do grafo
│   └── TestIntegration             # Testes E2E
│
├── 📋 requirements.txt         # Dependências Python
│
├── 🔐 .env.example             # Template de variáveis de ambiente
│
├── 📚 README.md                # Documentação principal
│   ├── Visão geral
│   ├── Instalação
│   ├── Exemplos de uso
│   └── Pontos de atenção
│
├── 🚀 DEPLOYMENT.md            # Guia de deploy
│   ├── Setup local
│   ├── Docker
│   ├── Cloud providers (Railway, Render, GCP, AWS)
│   ├── Setup Supabase
│   ├── Segurança
│   └── CI/CD
│
├── 📊 architecture_diagram.md  # Diagramas visuais
│   ├── Visão geral do sistema
│   ├── Fluxo de dados detalhado
│   ├── Arquitetura do Router Agent
│   ├── DSPy Module interno
│   └── Stack técnico
│
├── 🧠 ADVANCED_USAGE.md        # Uso avançado
│   ├── Multi-intent messages
│   ├── Context-aware detection
│   ├── Edge cases handling
│   ├── Customizações
│   ├── Monitoring
│   ├── Model fine-tuning
│   └── Security best practices
│
└── 🐳 Dockerfile               # Container configuration (opcional)
```

## 🎯 Arquivos Core (Prioridade Alta)

### 1. `router_agent.py` ⭐⭐⭐

**O que é:** Coração do sistema. Implementa toda a lógica de roteamento usando DSPy + LangGraph.

**Principais componentes:**
- `AgentState`: Schema do estado passado entre nós
- `RouterSignature`: DSPy signature com instruções para classificação PT-BR
- `RouterModule`: Wrapper DSPy com Chain of Thought
- `router_node`: Função que executa classificação
- `should_continue`: Lógica condicional de roteamento (priorização)
- `build_easyscale_graph`: Constrói o grafo completo

**Quando modificar:**
- Adicionar/remover tipos de intenção
- Ajustar prioridades de roteamento
- Adicionar novos agentes especializados
- Customizar instruções PT-BR

**Dependências:**
```python
import dspy
from langgraph.graph import StateGraph, END
```

### 2. `config.py` ⭐⭐

**O que é:** Configuração centralizada usando Pydantic Settings.

**Principais componentes:**
- `EasyScaleSettings`: Carrega de `.env` automaticamente
- `get_settings()`: Singleton pattern
- Suporte para múltiplos providers (OpenAI, Anthropic, Groq)

**Quando modificar:**
- Adicionar novas variáveis de ambiente
- Integrar novos serviços (ex: Redis, Kafka)
- Adicionar configurações de feature flags

### 3. `api.py` ⭐⭐

**O que é:** Interface REST API usando FastAPI.

**Principais endpoints:**
- `POST /api/v1/router`: Classificação manual
- `POST /api/v1/whatsapp/webhook`: Integração WhatsApp
- `GET /health`: Health check para monitoramento

**Quando modificar:**
- Adicionar autenticação/autorização
- Implementar rate limiting
- Adicionar novos endpoints
- Integrar com outras APIs (Twilio, WhatsApp Business)

### 4. `test_router.py` ⭐

**O que é:** Suite completa de testes.

**Categorias:**
- Unit tests (intent classification, urgency scoring)
- Integration tests (full pipeline)
- Edge cases (empty messages, emojis, spam)

**Como rodar:**
```bash
# Todos os testes
pytest test_router.py -v

# Somente unit tests
pytest test_router.py::TestIntentClassification -v

# Com coverage
pytest test_router.py --cov=router_agent --cov-report=html
```

## 📚 Arquivos de Documentação

### `README.md`
- **Audiência:** Desenvolvedores iniciantes no projeto
- **Conteúdo:** Setup rápido, exemplos básicos, visão geral

### `DEPLOYMENT.md`
- **Audiência:** DevOps, deployment engineers
- **Conteúdo:** Deploy em diferentes ambientes, configuração infra

### `architecture_diagram.md`
- **Audiência:** Arquitetos, tech leads
- **Conteúdo:** Diagramas ASCII, fluxos de dados, decisões arquiteturais

### `ADVANCED_USAGE.md`
- **Audiência:** Desenvolvedores experientes
- **Conteúdo:** Customizações avançadas, edge cases, otimizações

## 🔄 Fluxo de Trabalho Típico

### 1. Novo desenvolvedor entrando no projeto

```bash
# 1. Clone e setup
git clone <repo>
cd easyscale
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Edite .env com suas credenciais

# 3. Leia a documentação
cat README.md          # Visão geral
cat router_agent.py    # Código principal

# 4. Rode os testes
pytest test_router.py -v

# 5. Inicie o servidor
uvicorn api:app --reload

# 6. Teste via API
curl http://localhost:8000/docs
```

### 2. Adicionando nova intenção

```python
# router_agent.py

# 1. Adicione ao enum
class IntentType(str, Enum):
    SALES = "SALES"
    SCHEDULING = "SCHEDULING"
    # ... existing
    REFUND_REQUEST = "REFUND_REQUEST"  # ← NOVO

# 2. Atualize RouterSignature
class RouterSignature(dspy.Signature):
    # ...
    intents: List[str] = dspy.OutputField(
        desc=(
            # ... existing descriptions
            "- REFUND_REQUEST: Requests for refunds or cancellations. "
            "PT-BR indicators: 'quero cancelar', 'reembolso', 'devolução', "
            "'não fiquei satisfeito'.\n"
        )
    )

# 3. Crie o agente especializado
def refund_agent(state: AgentState) -> AgentState:
    """Handle refund requests."""
    # Implementação...
    pass

# 4. Adicione ao grafo
def build_easyscale_graph():
    workflow = StateGraph(AgentState)
    # ...
    workflow.add_node("refund_agent", refund_agent)

# 5. Atualize roteamento
def should_continue(state: AgentState):
    # ...
    if IntentType.REFUND_REQUEST.value in intent_queue:
        return "refund_agent"

# 6. Adicione edge
    workflow.add_edge("refund_agent", END)
    workflow.add_conditional_edges(
        "router",
        should_continue,
        {
            # ... existing
            "refund_agent": "refund_agent",
        }
    )
```

### 3. Mudando provider LLM

```bash
# .env
DSPY_PROVIDER=anthropic  # Era: openai
DSPY_MODEL=claude-3-5-sonnet-20241022  # Era: gpt-4o-mini
ANTHROPIC_API_KEY=sk-ant-...

# Restart servidor
# Tudo funciona automaticamente!
```

### 4. Deploy para produção

```bash
# 1. Configure secrets no Railway/Render
# OPENAI_API_KEY, SUPABASE_URL, etc.

# 2. Push para main branch
git push origin main

# 3. Deploy automático via CI/CD
# (configurado em .github/workflows/deploy.yml)

# 4. Monitore
# Railway dashboard ou logs:
railway logs --tail

# 5. Health check
curl https://easyscale-production.railway.app/health
```

## 🧩 Dependências Externas

### Python Packages

```
Core:
- fastapi          # REST API framework
- dspy-ai          # Structured LLM programming
- langgraph        # Agent orchestration
- pydantic         # Data validation

LLM Providers:
- openai           # GPT models
- anthropic        # Claude models
- groq             # Open source models (Llama)

Database:
- supabase         # PostgreSQL client
- psycopg2-binary  # PostgreSQL driver

Utilities:
- python-dotenv    # .env file loading
- httpx            # HTTP client

Testing:
- pytest           # Test framework
- pytest-asyncio   # Async test support
- pytest-cov       # Coverage reporting
```

### External Services

```
Required:
- Supabase (or PostgreSQL 14+)
- OpenAI/Anthropic/Groq API key

Optional:
- WhatsApp Business API
- Sentry (error tracking)
- LangSmith (LLM observability)
```

## 📊 Métricas de Código

```
Total Lines:
- router_agent.py: ~600 lines
- api.py: ~300 lines
- config.py: ~100 lines
- test_router.py: ~500 lines
- Documentation: ~3000 lines

Total: ~4500 lines

Complexity:
- Cyclomatic complexity: Low-Medium
- Test coverage target: >80%
- Type hints: 100% (all public APIs)
```

## 🔐 Arquivos Sensíveis (Git Ignored)

```
.env                    # Variáveis de ambiente REAIS
.venv/                  # Virtual environment
__pycache__/            # Python cache
*.pyc                   # Compiled Python
.pytest_cache/          # Pytest cache
.coverage               # Coverage data
htmlcov/                # Coverage HTML report
.DS_Store               # macOS
*.log                   # Log files
```

## 🎓 Ordem de Leitura Recomendada

### Para entender o projeto:

1. **README.md** (10 min) - Visão geral e setup
2. **architecture_diagram.md** (15 min) - Arquitetura visual
3. **router_agent.py** (30 min) - Código principal
4. **api.py** (15 min) - Interface REST
5. **test_router.py** (20 min) - Casos de teste

### Para fazer deploy:

1. **DEPLOYMENT.md** (20 min) - Todas as opções de deploy
2. **.env.example** (5 min) - Variáveis necessárias
3. **requirements.txt** (2 min) - Dependências

### Para customizar:

1. **ADVANCED_USAGE.md** (30 min) - Customizações e edge cases
2. **router_agent.py** (deep dive) - Modificar lógica
3. **test_router.py** - Adicionar testes para suas customizações

## 📞 Contato e Suporte

- **Issues técnicos:** Abra issue no GitHub
- **Dúvidas de implementação:** [seu-email]
- **Documentação oficial:**
  - DSPy: https://dspy-docs.vercel.app
  - LangGraph: https://langchain-ai.github.io/langgraph/
  - FastAPI: https://fastapi.tiangolo.com

---

**Última atualização:** 2026-01-20
**Versão:** 1.0.0
**Mantenedor:** EasyScale Team
