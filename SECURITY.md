# EasyScale - Guia de Segurança 🔐

## 🛡️ Proteções Implementadas

O sistema EasyScale possui várias camadas de segurança implementadas:

### 1. Security Middleware

O `SecurityMiddleware` protege contra:
- **Path Traversal**: Bloqueia tentativas de acessar `.git`, `.env`, credenciais AWS, etc.
- **Vulnerability Scanners**: Detecta e bloqueia ferramentas como Nikto, SQLMap, Nmap
- **Suspicious Extensions**: Bloqueia arquivos `.php`, `.asp`, `.sh`, etc.
- **Temporary IP Blocking**: IPs suspeitos são bloqueados temporariamente

```python
# security_middleware.py
SUSPICIOUS_PATHS = [
    ".git", ".env", "aws", "terraform", "docker", "wp-admin",
    "phpinfo", "config", "credentials", "root/", "admin"
]
```

### 2. Rate Limiting

Proteção contra abuso e ataques DDoS:
- **60 requests por minuto** por IP (padrão)
- Headers informativos: `X-RateLimit-Limit`, `X-RateLimit-Remaining`
- Resposta 429 quando limite excedido

```python
# Customizar rate limit
app.add_middleware(SecurityMiddleware, rate_limit=120)  # 120 req/min
```

### 3. Security Headers

Adiciona automaticamente headers de segurança:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
```

### 4. Access Logging

Middleware de logging que:
- Registra apenas requisições relevantes (API endpoints)
- Ignora ruído (favicon, robots.txt)
- Mostra duração, status code e IP do cliente

```
📊 POST /v1/reengage → 200 (843ms) [10.11.0.7]
🚨 SECURITY: Blocked IP 10.11.0.7 until 2026-01-20 19:30:00
```

## 🚨 O que os Logs Mostram

Os logs que você compartilhou indicam:

### ✅ Sistema Funcionando Corretamente
```
INFO: POST /v1/reengage HTTP/1.1" 200 OK
--- STARTING ANALYSIS FOR: João Silva ---
--- STRATEGY CHOSEN: Selected Strategy: EDUCATION ---
```
✅ O endpoint `/v1/reengage` está respondendo corretamente

### ⚠️ Tentativas de Scanner/Bot
```
INFO: GET /.git/config HTTP/1.1" 404 Not Found
INFO: GET /.env HTTP/1.1" 404 Not Found
INFO: GET /aws/credentials HTTP/1.1" 404 Not Found
INFO: GET /.terraform/terraform.tfstate HTTP/1.1" 404 Not Found
INFO: GET /root/.aws/credentials HTTP/1.1" 404 Not Found
```
⚠️ **Bot tentando encontrar vulnerabilidades** (comum na internet pública)

### ✅ Proteção Funcionando
- Todos retornam **404 Not Found** (bom!)
- Com o novo middleware, esses IPs serão **bloqueados automaticamente**

## 🔧 Como Ativar as Proteções

### 1. Adicione o Middleware à sua API

O arquivo `api.py` já foi atualizado com:
```python
from security_middleware import SecurityMiddleware, AccessLogMiddleware

# Security middleware (MUST be first)
app.add_middleware(SecurityMiddleware, rate_limit=60)
app.add_middleware(AccessLogMiddleware, log_level="INFO")
```

### 2. Reinicie o Servidor

```bash
# Pare o servidor atual (CTRL+C)
# Reinicie
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### 3. Teste a Proteção

```bash
# Tentativa de acessar .git (deve ser bloqueado)
curl http://localhost:8000/.git/config
# Resposta: {"detail": "Access denied"}

# IP é bloqueado por 30 minutos
curl http://localhost:8000/api/v1/router
# Resposta: {"detail": "IP temporarily blocked due to suspicious activity"}
```

## 📊 Monitoramento

### Logs de Segurança

Com o novo middleware, você verá:
```
📊 POST /v1/reengage → 200 (843ms) [10.11.0.7]
🚨 SECURITY: Blocked IP 10.11.0.8 until 2026-01-20 19:30:00
```

### Rate Limiting

```bash
curl -I http://localhost:8000/api/v1/test/classify
# Headers de resposta:
# X-RateLimit-Limit: 60
# X-RateLimit-Remaining: 59
```

### Rate Limit Excedido

```bash
# Após 60 requests em 1 minuto
curl http://localhost:8000/api/v1/router
# Resposta 429:
{
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

## 🔐 Boas Práticas Adicionais

### 1. Configure CORS Corretamente

```python
# api.py - NÃO use "*" em produção!
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://seu-frontend.com",
        "https://dashboard.easyscale.com"
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)
```

### 2. Use HTTPS em Produção

```bash
# Railway/Render: HTTPS automático
# AWS/GCP: Use ALB/Load Balancer com certificado SSL
# Self-hosted: Use Nginx + Let's Encrypt

# Nginx config:
server {
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/seu-dominio/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
    }
}
```

### 3. Variáveis de Ambiente Seguras

```bash
# .env - NUNCA commite este arquivo!
# Use secrets managers em produção:

# Railway
railway secrets set OPENAI_API_KEY=sk-...

# AWS
aws secretsmanager create-secret \
  --name easyscale/openai-key \
  --secret-string sk-...

# GCP
gcloud secrets create openai-api-key \
  --data-file=-
```

### 4. Monitore Tentativas de Ataque

```python
# Adicione alertas para IPs bloqueados
from security_middleware import SecurityMiddleware

class AlertingSecurityMiddleware(SecurityMiddleware):
    def _block_ip(self, ip: str, minutes: int):
        super()._block_ip(ip, minutes)

        # Envie alerta (Slack, email, etc.)
        self.send_alert(
            f"⚠️ IP bloqueado: {ip}",
            f"Tentativa de acesso suspeito"
        )
```

## 🚨 Respondendo a Incidentes

### Cenário 1: Muitas Tentativas de Scanner

**Sintoma:** Muitos logs de tentativas de acesso a `.git`, `.env`, etc.

**Ação:**
1. ✅ Middleware já está bloqueando automaticamente
2. ✅ IPs são bloqueados por 30-60 minutos
3. 📊 Monitore os logs para padrões
4. 🔧 Se persistir, considere usar Cloudflare (proteção DDoS)

### Cenário 2: Rate Limit Sendo Atingido por Usuários Legítimos

**Sintoma:** Clientes reclamando de erro 429

**Ação:**
```python
# Aumente o limite
app.add_middleware(SecurityMiddleware, rate_limit=120)  # 120/min

# Ou implemente rate limit por usuário (não por IP)
```

### Cenário 3: Ataque DDoS

**Sintoma:** Servidor lento, muitos requests de múltiplos IPs

**Ação:**
1. 🛡️ Habilite Cloudflare (proteção DDoS gratuita)
2. 🔧 Configure firewall do servidor (iptables, AWS Security Groups)
3. 📊 Use serviços de proteção DDoS (Cloudflare, AWS Shield)

## 📋 Checklist de Segurança

### Desenvolvimento
- [ ] `.env` no `.gitignore`
- [ ] Secrets não hardcoded no código
- [ ] HTTPS em desenvolvimento (ngrok ou similar)
- [ ] Security middleware habilitado

### Staging
- [ ] HTTPS obrigatório
- [ ] CORS configurado corretamente
- [ ] Rate limiting testado
- [ ] Logs de segurança revisados

### Produção
- [ ] HTTPS com certificado válido
- [ ] Secrets em secrets manager (não em .env)
- [ ] CORS restrito a domínios conhecidos
- [ ] Rate limiting configurado
- [ ] Firewall configurado
- [ ] Monitoring habilitado (Sentry)
- [ ] Backups automáticos
- [ ] IP blocking funcionando
- [ ] Security headers configurados

## 🆘 Suporte

### Dúvidas sobre Segurança
- 📖 Leia este guia completamente
- 🔍 Revise os logs do middleware
- 📧 Contato: [seu-email]

### Reportar Vulnerabilidade
Se você encontrou uma vulnerabilidade de segurança, por favor:
1. **NÃO abra issue público**
2. Envie email para: security@easyscale.com
3. Inclua: descrição, passos para reproduzir, impacto

---

**Última atualização:** 2026-01-20
**Versão:** 1.0.0
**Status:** ✅ Protegido
