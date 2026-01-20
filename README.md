# EasyScale - Router Agent System

Sistema de roteamento inteligente para atendimento de clínicas de estética via WhatsApp, utilizando **DSPy** para decisões lógicas e **LangGraph** para orquestração de agentes.

## 🎯 Visão Geral

O Router Agent é o cérebro do EasyScale que:
- Interpreta mensagens de pacientes em **Português Brasileiro (PT-BR)**
- Classifica intenções automaticamente usando LLM
- Roteia para agentes especializados (vendas, agendamento, suporte médico, FAQ)
- Prioriza urgências médicas para segurança do paciente

## 🏗️ Arquitetura

```
WhatsApp Message (PT-BR)
    ↓
Router Agent (DSPy)
    ↓
Intent Classification + Urgency Score
    ↓
Conditional Routing (LangGraph)
    ↓
┌─────────────┬──────────────┬──────────────┬──────────────┐
│   Medical   │  Scheduler   │    Closer    │     FAQ      │
│    Agent    │    Agent     │    Agent     │    Agent     │
└─────────────┴──────────────┴──────────────┴──────────────┘
```

### Tipos de Intenção

| Intenção | Descrição | Exemplos PT-BR |
|----------|-----------|----------------|
| `MEDICAL_ASSESSMENT` | Urgências médicas, reações adversas | "fiquei com alergia", "está muito inchado", "muita dor" |
| `SCHEDULING` | Agendamentos, remarcações | "quero marcar", "tem horário?", "desmarcar consulta" |
| `SALES` | Preços, descontos, pacotes | "quanto custa?", "tá caro", "tem promoção?" |
| `TECH_FAQ` | Dúvidas técnicas sobre procedimentos | "como funciona?", "dói?", "quanto tempo dura?" |
| `GENERAL_INFO` | Informações gerais da clínica | "onde fica?", "horário de funcionamento" |

### Priorização

O sistema segue esta ordem de prioridade (do mais urgente ao menos):

1. **MEDICAL_ASSESSMENT** ⚠️ - Sempre priorizado (segurança do paciente)
2. **SCHEDULING** 📅 - Time-sensitive
3. **SALES** 💰 - Comercial
4. **TECH_FAQ** ❓ - Informacional
5. **GENERAL_INFO** ℹ️ - Geral

## 🚀 Instalação

### Pré-requisitos

```bash
Python 3.10+
pip install dspy-ai langgraph fastapi supabase pydantic pydantic-settings
```

### Configuração

1. **Clone o repositório e instale dependências:**

```bash
git clone <your-repo>
cd easyscale
pip install -r requirements.txt
```

2. **Configure variáveis de ambiente:**

```bash
cp .env.example .env
# Edite .env com suas credenciais
```

3. **Configure o DSPy com seu provedor de LLM:**

```python
from router_agent import configure_dspy

# Opção 1: OpenAI
configure_dspy(
    provider="openai",
    model="gpt-4o-mini",
    api_key="sk-..."
)

# Opção 2: Anthropic
configure_dspy(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    api_key="sk-ant-..."
)

# Opção 3: Groq (open source)
configure_dspy(
    provider="groq",
    model="llama-3.3-70b-versatile",
    api_key="gsk_..."
)
```

## 📖 Uso

### Exemplo Básico

```python
from router_agent import build_easyscale_graph, configure_dspy
import os

# 1. Configure DSPy
configure_dspy(
    provider="openai",
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY")
)

# 2. Construa o grafo
graph = build_easyscale_graph()

# 3. Prepare o contexto do paciente (da view_context_hydration)
patient_context = {
    "patient_id": "p_12345",
    "active_items": [
        {
            "service_name": "Botox",
            "price": 800.0,
            "status": "quoted"
        }
    ],
    "behavioral_profile": {
        "communication_style": "direct",
        "price_sensitivity": "medium",
        "decision_speed": "fast"
    }
}

# 4. Execute o roteamento
result = graph.invoke({
    "context": patient_context,
    "latest_message": "quanto custa e dá pra parcelar?",
    "intent_queue": [],
    "final_response": "",
    "urgency_score": 0,
    "reasoning": ""
})

# 5. Analise o resultado
print(f"Intenções detectadas: {result['intent_queue']}")
# Output: ['SALES']

print(f"Urgência: {result['urgency_score']}/5")
# Output: Urgência: 2/5

print(f"Raciocínio: {result['reasoning']}")
# Output: Customer asking about price and payment options. Keywords: 'quanto custa', 'parcelar'

print(f"Resposta: {result['final_response']}")
# Output: [CLOSER AGENT] Processing sales inquiry...
```

### Exemplos de Mensagens PT-BR

```python
# Exemplo 1: Vendas
result = graph.invoke({
    "context": patient_context,
    "latest_message": "tá muito caro, tem desconto pra pagamento à vista?",
    ...
})
# → Rota para: closer_agent

# Exemplo 2: Agendamento
result = graph.invoke({
    "context": patient_context,
    "latest_message": "quero marcar para sexta-feira de manhã, tem vaga?",
    ...
})
# → Rota para: scheduler_agent

# Exemplo 3: Urgência Médica (PRIORIDADE!)
result = graph.invoke({
    "context": patient_context,
    "latest_message": "fiz o procedimento ontem e hoje acordei com o rosto muito inchado",
    ...
})
# → Rota para: medical_agent (urgency_score: 4-5)

# Exemplo 4: FAQ Técnico
result = graph.invoke({
    "context": patient_context,
    "latest_message": "o botox dói? quanto tempo dura o resultado?",
    ...
})
# → Rota para: faq_agent
```

## 🧪 Testes

```bash
# Executar todos os testes
pytest test_router.py -v

# Testes específicos
pytest test_router.py::TestIntentClassification -v
pytest test_router.py::TestRoutingLogic -v

# Testes de integração (requer API key)
pytest test_router.py -v -m integration

# Com coverage
pytest test_router.py --cov=router_agent --cov-report=html
```

## 🔍 Pontos de Atenção

### ✅ O que verificar no código gerado:

1. **Instanciação do DSPy:**
   ```python
   # Correto ✓
   configure_dspy(provider="openai", model="gpt-4o-mini")
   # Isso chama internamente: dspy.settings.configure(lm=...)
   ```

2. **Arestas do Grafo:**
   ```python
   # Correto ✓
   workflow.add_conditional_edges(
       "router",
       should_continue,
       {
           "medical_agent": "medical_agent",
           "scheduler_agent": "scheduler_agent",
           # ...
       }
   )
   ```

3. **Acumulação de Intents:**
   ```python
   # Correto ✓
   intent_queue: Annotated[List[str], operator.add]
   # Permite múltiplos nós adicionarem à fila
   ```

4. **Priorização de Urgências:**
   ```python
   # Correto ✓
   if IntentType.MEDICAL_ASSESSMENT.value in intent_queue:
       return "medical_agent"  # Sempre primeiro!
   ```

## 🔐 Segurança e Privacidade

- **Dados Sensíveis:** O contexto pode conter informações médicas (PHI). Use criptografia em trânsito e em repouso.
- **API Keys:** Nunca commite `.env` ao Git. Use secrets managers em produção.
- **Logs:** O campo `reasoning` contém lógica interna em inglês para auditoria, mas não deve expor dados do paciente.

## 📊 Integração com Supabase

O `context` vem da view `view_context_hydration`:

```sql
-- Exemplo da estrutura esperada
CREATE VIEW view_context_hydration AS
SELECT
    p.id AS patient_id,
    jsonb_agg(DISTINCT jsonb_build_object(
        'service_name', s.name,
        'price', s.price,
        'status', ps.status
    )) AS active_items,
    jsonb_build_object(
        'communication_style', p.comm_style,
        'price_sensitivity', p.price_sensitivity,
        'decision_speed', p.decision_speed
    ) AS behavioral_profile,
    -- outros campos...
FROM patients p
LEFT JOIN patient_services ps ON p.id = ps.patient_id
LEFT JOIN services s ON ps.service_id = s.id
GROUP BY p.id;
```

## 🚧 TODOs / Próximos Passos

- [ ] Implementar `closer_agent` completo (vendas)
- [ ] Implementar `scheduler_agent` com integração Supabase
- [ ] Implementar `medical_agent` com protocolos de triagem
- [ ] Implementar `faq_agent` com retrieval de base de conhecimento
- [ ] Adicionar memória de conversação (histórico multi-turno)
- [ ] Implementar fallback para quando nenhuma intenção for detectada
- [ ] Adicionar métricas e observabilidade (LangSmith, Phoenix)
- [ ] Testes A/B de diferentes modelos (GPT-4 vs Claude vs Llama)

## 📝 Boas Práticas Seguidas

✅ **Variáveis e documentação em inglês** (código internacional)
✅ **Otimizado para PT-BR** (instruções do DSPy específicas para coloquialismos brasileiros)
✅ **Type hints completos** (TypedDict, Literal, Annotated)
✅ **Docstrings detalhados** (Google style)
✅ **Separação de responsabilidades** (config.py, router_agent.py, test_router.py)
✅ **Testes unitários e de integração**
✅ **Logging e rastreabilidade** (campo `reasoning`)
✅ **Priorização de segurança do paciente** (MEDICAL_ASSESSMENT sempre primeiro)

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch de feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Add: nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 Licença

[Especifique sua licença aqui]

## 📧 Contato

Para dúvidas sobre implementação: [seu-email]

---

**Desenvolvido com ❤️ para clínicas de estética que querem oferecer atendimento de excelência via WhatsApp.**
