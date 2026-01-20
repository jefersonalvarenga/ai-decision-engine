# EasyScale - Guia de Troubleshooting 🔧

## 🚨 Erros Comuns de Deploy

### Erro: "Module not found" ou ImportError

**Sintoma:**
```
ImportError: No module named 'fastapi'
ImportError: No module named 'dspy'
ModuleNotFoundError: No module named 'security_middleware'
```

**Causa:** Dependências não instaladas no ambiente de deploy

**Solução:**

1. **Verifique o requirements.txt:**
   ```bash
   cat requirements.txt
   ```

2. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Execute o checker:**
   ```bash
   python check_dependencies.py
   ```

4. **Se o problema persistir:**
   ```bash
   # Force reinstall
   pip install -r requirements.txt --force-reinstall --no-cache-dir
   ```

---

### Erro: "uvicorn: command not found"

**Sintoma:**
```
/bin/sh: uvicorn: not found
```

**Causa:** uvicorn não está instalado ou não está no PATH

**Solução:**

```bash
# 1. Instale uvicorn
pip install uvicorn[standard]

# 2. Verifique instalação
which uvicorn
uvicorn --version

# 3. Se não encontrar, use Python -m
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

---

### Erro: "Port already in use"

**Sintoma:**
```
ERROR: [Errno 48] Address already in use
```

**Causa:** Porta 8000 já está em uso

**Solução:**

```bash
# Linux/Mac - Encontrar e matar processo
lsof -ti:8000 | xargs kill -9

# Windows - Encontrar processo
netstat -ano | findstr :8000
# Matar processo
taskkill /PID <PID> /F

# Ou use outra porta
uvicorn api:app --port 8001
```

---

### Erro: "DSPY_MODEL or OPENAI_API_KEY not set"

**Sintoma:**
```
ValueError: OPENAI_API_KEY environment variable not set
KeyError: 'DSPY_PROVIDER'
```

**Causa:** Variáveis de ambiente não configuradas

**Solução:**

1. **Verifique o .env:**
   ```bash
   cat .env
   # Deve conter:
   DSPY_PROVIDER=openai
   DSPY_MODEL=gpt-4o-mini
   OPENAI_API_KEY=sk-proj-...
   ```

2. **Se .env não existe:**
   ```bash
   cp .env.example .env
   nano .env  # Edite com suas credenciais
   ```

3. **Para Railway/Render, configure via dashboard:**
   - Vá em Settings → Variables
   - Adicione: `OPENAI_API_KEY`, `DSPY_PROVIDER`, etc.

---

### Erro: "Cannot connect to Supabase"

**Sintoma:**
```
ConnectionError: Unable to connect to Supabase
supabase.errors.AuthError: Invalid API key
```

**Causa:** Credenciais do Supabase incorretas ou não configuradas

**Solução:**

1. **Verifique credenciais:**
   ```bash
   echo $SUPABASE_URL
   echo $SUPABASE_KEY
   ```

2. **Teste conexão:**
   ```python
   from supabase import create_client
   import os

   url = os.getenv("SUPABASE_URL")
   key = os.getenv("SUPABASE_KEY")

   client = create_client(url, key)
   print("✅ Connected to Supabase!")
   ```

3. **Se falhar, pegue novas credenciais:**
   - Acesse https://app.supabase.com
   - Projeto → Settings → API
   - Copie URL e anon key

---

### Erro: "429 Too Many Requests" nos testes

**Sintoma:**
```
{"detail": "Rate limit exceeded. Please try again later."}
```

**Causa:** Rate limiting está bloqueando seus testes

**Solução:**

1. **Temporariamente aumente o limite:**
   ```python
   # api.py
   app.add_middleware(SecurityMiddleware, rate_limit=1000)  # Para testes
   ```

2. **Ou desabilite rate limiting em dev:**
   ```python
   # api.py
   import os

   if os.getenv("ENVIRONMENT") == "production":
       app.add_middleware(SecurityMiddleware, rate_limit=60)
   else:
       print("⚠️  Rate limiting disabled in development")
   ```

---

### Erro: "403 Forbidden" ao acessar endpoints

**Sintoma:**
```
{"detail": "IP temporarily blocked due to suspicious activity"}
```

**Causa:** SecurityMiddleware bloqueou seu IP

**Solução:**

1. **Verifique por que foi bloqueado:**
   - Tentou acessar `.git`, `.env`?
   - Fez muitos requests seguidos?

2. **Desbloqueie seu IP (desenvolvimento):**
   ```python
   # Reinicie o servidor (o bloqueio é em memória)
   # CTRL+C e reinicie
   ```

3. **Whitelist seu IP (produção):**
   ```python
   # security_middleware.py
   WHITELISTED_IPS = ["127.0.0.1", "seu-ip"]

   if client_ip in WHITELISTED_IPS:
       return await call_next(request)
   ```

---

## 🐛 Debug Mode

### Habilitar logs detalhados:

```bash
# .env
DEBUG_MODE=true
LOG_LEVEL=DEBUG

# Restart servidor
uvicorn api:app --reload --log-level debug
```

### Ver stack traces completos:

```python
# api.py
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )
```

---

## 📊 Verificar Status do Sistema

### Health Check:

```bash
curl http://localhost:8000/health

# Deve retornar:
{
  "status": "healthy",
  "version": "1.0.0",
  "dspy_configured": true,
  "timestamp": "2026-01-20T18:30:00"
}
```

### Test Classification:

```bash
curl -X POST "http://localhost:8000/api/v1/test/classify?message=quanto%20custa"

# Deve retornar:
{
  "message": "quanto custa",
  "intents": ["SALES"],
  "urgency": 2,
  "reasoning": "Customer asking about pricing..."
}
```

---

## 🚀 Deploy em Diferentes Plataformas

### Railway

**Problema comum:** Buildpack não reconhece Python

**Solução:**
```bash
# Adicione railway.toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn api:app --host 0.0.0.0 --port $PORT"
```

### Render

**Problema comum:** Timeout no build

**Solução:**
```yaml
# render.yaml
services:
  - type: web
    name: easyscale-api
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn api:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.7
```

### Heroku

**Problema comum:** Slug size muito grande

**Solução:**
```bash
# Reduza dependências desnecessárias
# requirements.txt - remova unused:
# pytest  # Só em dev
# black   # Só em dev
```

### Docker

**Problema comum:** Imagem muito grande

**Solução:**
```dockerfile
# Use slim base image
FROM python:3.11-slim

# Multi-stage build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "api:app", "--host", "0.0.0.0"]
```

---

## 📞 Ainda com Problemas?

### 1. Execute o checker:
```bash
python check_dependencies.py
```

### 2. Verifique logs:
```bash
# Local
tail -f api.log

# Railway
railway logs --tail

# Render
render logs --tail
```

### 3. Teste localmente primeiro:
```bash
# Simule ambiente de produção
export ENVIRONMENT=production
export DSPY_PROVIDER=openai
export OPENAI_API_KEY=sk-...

uvicorn api:app --host 0.0.0.0 --port 8000
```

### 4. Reporte o erro:
- 📧 Email: [seu-email]
- 🐛 GitHub Issues: [seu-repo]/issues
- 📚 Documentação: README.md, DEPLOYMENT.md

---

**Última atualização:** 2026-01-20
**Versão:** 1.0.0
