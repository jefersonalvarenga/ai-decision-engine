# EasyScale - Guia de Deploy

Este documento detalha como fazer o deploy do sistema EasyScale em diferentes ambientes.

## 📋 Pré-requisitos

- Python 3.10+
- Conta Supabase (ou PostgreSQL 14+)
- API Key de LLM (OpenAI, Anthropic, ou Groq)
- Servidor com mínimo 1GB RAM

## 🔧 Setup Local (Desenvolvimento)

### 1. Clone e Instale Dependências

```bash
git clone <your-repo>
cd easyscale
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 2. Configure Variáveis de Ambiente

```bash
cp .env.example .env
# Edite .env com suas credenciais
nano .env
```

### 3. Teste o Router

```bash
# Teste básico
python router_agent.py

# Rode os testes
pytest test_router.py -v
```

### 4. Inicie o Servidor FastAPI

```bash
# Desenvolvimento (auto-reload)
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Acesse: http://localhost:8000/docs
```

## 🐳 Deploy com Docker

### Dockerfile

Crie um `Dockerfile` na raiz do projeto:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Expor porta
EXPOSE 8000

# Comando de inicialização
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  easyscale-api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - LOG_LEVEL=INFO
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Build e Run

```bash
# Build
docker build -t easyscale-router:latest .

# Run
docker run -d \
  --name easyscale-api \
  -p 8000:8000 \
  --env-file .env \
  easyscale-router:latest

# Ou use docker-compose
docker-compose up -d
```

## ☁️ Deploy em Cloud Providers

### Railway.app (Recomendado para MVPs)

1. **Conecte seu repositório:**
   - Acesse [railway.app](https://railway.app)
   - New Project → Deploy from GitHub

2. **Configure variáveis:**
   ```
   DSPY_PROVIDER=openai
   DSPY_MODEL=gpt-4o-mini
   OPENAI_API_KEY=sk-...
   SUPABASE_URL=https://...
   SUPABASE_KEY=eyJ...
   ```

3. **Configure o Start Command:**
   ```
   uvicorn api:app --host 0.0.0.0 --port $PORT
   ```

4. **Deploy automático** acontecerá a cada push na branch principal.

### Render.com

1. **Crie um novo Web Service**
2. **Configurações:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
3. **Adicione variáveis de ambiente** na dashboard
4. **Deploy automático** via GitHub

### Google Cloud Run

```bash
# 1. Build e push para Container Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/easyscale-router

# 2. Deploy
gcloud run deploy easyscale-router \
  --image gcr.io/PROJECT_ID/easyscale-router \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DSPY_PROVIDER=openai,DSPY_MODEL=gpt-4o-mini" \
  --set-secrets "OPENAI_API_KEY=projects/PROJECT_ID/secrets/openai-key:latest"
```

### AWS ECS (Fargate)

1. **Push para ECR:**
   ```bash
   aws ecr create-repository --repository-name easyscale-router
   docker tag easyscale-router:latest AWS_ACCOUNT.dkr.ecr.REGION.amazonaws.com/easyscale-router:latest
   docker push AWS_ACCOUNT.dkr.ecr.REGION.amazonaws.com/easyscale-router:latest
   ```

2. **Crie Task Definition** (via console ou Terraform)
3. **Configure ALB** para distribuir tráfego
4. **Configure Auto Scaling** baseado em CPU/memória

## 🗄️ Setup do Banco (Supabase)

### 1. Crie a View de Contexto

Execute no SQL Editor do Supabase:

```sql
-- View para hidratar o contexto do paciente
CREATE OR REPLACE VIEW view_context_hydration AS
SELECT
    p.id AS patient_id,
    p.name,
    p.phone,
    p.email,

    -- Serviços ativos
    COALESCE(
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'service_id', s.id,
                'service_name', s.name,
                'price', s.price,
                'status', ps.status,
                'quoted_at', ps.quoted_at
            )
        ) FILTER (WHERE s.id IS NOT NULL),
        '[]'::jsonb
    ) AS active_items,

    -- Perfil comportamental
    jsonb_build_object(
        'communication_style', p.communication_style,
        'price_sensitivity', p.price_sensitivity,
        'decision_speed', p.decision_speed,
        'preferred_contact_time', p.preferred_contact_time
    ) AS behavioral_profile,

    -- Histórico de conversação (últimas 10 mensagens)
    COALESCE(
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'role', cl.role,
                    'text', cl.message,
                    'timestamp', cl.created_at
                )
                ORDER BY cl.created_at DESC
            )
            FROM (
                SELECT * FROM conversation_logs
                WHERE patient_id = p.id
                ORDER BY created_at DESC
                LIMIT 10
            ) cl
        ),
        '[]'::jsonb
    ) AS conversation_history,

    -- Dados demográficos
    jsonb_build_object(
        'age', p.age,
        'gender', p.gender,
        'location', p.city
    ) AS patient_demographics

FROM patients p
LEFT JOIN patient_services ps ON p.id = ps.patient_id AND ps.status IN ('quoted', 'interested')
LEFT JOIN services s ON ps.service_id = s.id
GROUP BY p.id, p.name, p.phone, p.email;

-- Permissões
GRANT SELECT ON view_context_hydration TO authenticated;
```

### 2. Crie a Tabela de Logs

```sql
CREATE TABLE conversation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('patient', 'agent', 'system')),
    message TEXT NOT NULL,
    intents TEXT[] DEFAULT '{}',
    urgency_score INT CHECK (urgency_score BETWEEN 1 AND 5),
    reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversation_patient ON conversation_logs(patient_id, created_at DESC);
CREATE INDEX idx_conversation_urgency ON conversation_logs(urgency_score DESC) WHERE urgency_score >= 4;
```

## 🔐 Segurança

### 1. API Keys

**Nunca commite secrets!** Use:
- **Local:** `.env` (gitignored)
- **Cloud:** Secrets Manager (AWS Secrets, GCP Secret Manager, Railway Secrets)

### 2. Rate Limiting

Adicione ao `api.py`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/v1/router")
@limiter.limit("10/minute")  # Max 10 requests por minuto
async def route_message(...):
    ...
```

### 3. HTTPS

- **Local:** Use ngrok ou similar para testes
- **Produção:** Use certificados SSL (Let's Encrypt via Certbot, ou automático em Railway/Render)

### 4. CORS

Ajuste em `api.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://seu-frontend.com",
        "https://dashboard.easyscale.com"
    ],  # Não use "*" em produção!
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## 📊 Monitoramento

### 1. Logs Estruturados

```python
import logging
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger("easyscale")

# No código:
logger.info(json.dumps({
    "event": "message_routed",
    "patient_id": patient_id,
    "intents": intents,
    "urgency": urgency_score
}))
```

### 2. Sentry (Error Tracking)

```bash
pip install sentry-sdk[fastapi]
```

```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://...@sentry.io/...",
    traces_sample_rate=1.0,
)
```

### 3. LangSmith (LLM Observability)

```bash
pip install langsmith
```

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "ls_..."
os.environ["LANGCHAIN_PROJECT"] = "easyscale-production"
```

## 🚀 CI/CD

### GitHub Actions

Crie `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest test_router.py

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Railway
        run: |
          npm i -g @railway/cli
          railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

## 📈 Escalabilidade

### Horizontal Scaling

- **Railway/Render:** Auto-scaling configurado na dashboard
- **Kubernetes:** Use HPA (Horizontal Pod Autoscaler)
  ```yaml
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: easyscale-hpa
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: easyscale-router
    minReplicas: 2
    maxReplicas: 10
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  ```

### Otimização de Custos LLM

1. **Use modelos menores para classificação:**
   - `gpt-4o-mini` em vez de `gpt-4`
   - `claude-3-haiku` em vez de `claude-3-sonnet`
   - `llama-3.1-8b` (Groq) - gratuito até certo volume

2. **Cache de respostas frequentes:**
   ```python
   from functools import lru_cache

   @lru_cache(maxsize=1000)
   def classify_common_phrases(message: str):
       # Cache para mensagens comuns
       pass
   ```

3. **Batching de requests** (se aplicável)

## ✅ Checklist de Deploy

- [ ] Variáveis de ambiente configuradas
- [ ] Supabase views criadas
- [ ] Testes passando (`pytest`)
- [ ] HTTPS habilitado
- [ ] CORS configurado corretamente
- [ ] Rate limiting ativado
- [ ] Logs estruturados
- [ ] Error tracking (Sentry)
- [ ] Backup do banco configurado
- [ ] Monitoring/alertas configurados
- [ ] Documentação da API atualizada (/docs)
- [ ] Load testing realizado

## 🆘 Troubleshooting

### Erro: "DSPy not configured"
```bash
# Certifique-se de que a API key está correta
echo $OPENAI_API_KEY
# Configure explicitamente no código
configure_dspy(provider="openai", model="gpt-4o-mini", api_key="sk-...")
```

### Erro: "Connection to Supabase failed"
```bash
# Teste a conexão
curl -H "apikey: YOUR_KEY" https://YOUR_PROJECT.supabase.co/rest/v1/
```

### Alto tempo de resposta
- Use `gpt-4o-mini` em vez de `gpt-4`
- Implemente cache de contexto
- Considere usar Groq (latência ultra-baixa)

---

**Última atualização:** 2026-01-20
**Mantenedor:** EasyScale Team
