Tenho tudo que preciso. Aqui está o resumo completo:

---

## Resumo Completo — SDR Gatekeeper (n8n)

### Repositório
- **Local:** `/Users/jefersonalvarenga/Documents/easyscale-n8n-sdr-gatekeeper`
- **Branch principal:** `main` (tudo está commitado e em dia com origin)
- **Branch auxiliar:** `feat/test-inbound-workflow` (criada durante testes, pode ser deletada)
- **Último commit:** `d653140` — integração `pick_next_clinic()` no greeting

---

### O que foi construído

#### 4 Workflows no n8n

| Arquivo | Nome no n8n | Status |
|---|---|---|
| `workflows/gitops-deployer.json` | GitOps Deployer | ✅ Ativo |
| `workflows/sdr-gatekeeper-inbound.json` | SDR Gatekeeper - Inbound Handler | ✅ Ativo |
| `workflows/sdr-gatekeeper-greeting.json` | SDR Gatekeeper - Greeting Outbound | ✅ Ativo |
| `workflows/sdr-gatekeeper-expiration.json` | SDR Gatekeeper - Expiração de Conversas | ✅ Ativo |

#### GitOps Deployer
- Webhook no GitHub dispara o deployer quando há push na `main`
- Ciclo automático: **deactivate → update → activate** (força publicação)
- Remove campos read-only antes do PUT (`active`, `tags`, `staticData`, `meta`, `pinData`)

#### Inbound Handler — Fluxo
```
Webhook Evolution API
  → Parse Evolution Payload
  → Filtro Mensagem Válida?
  → É Reset?
      ├─ SIM → Supabase DELETE cascade → Evolution "Conversa resetada." → Respond OK
      └─ NÃO → Busca Conversa → Merge Contexto → Nova Conversa?
                  ├─ SIM → INSERT gk_conversations
                  └─ NÃO → UPDATE gk_conversations
                INSERT gk_messages (inbound)
                SELECT gk_messages (histórico)
                Prepara Payload FastAPI
                HTTP POST FastAPI /v1/sdr/gatekeeper
                Processa Resposta FastAPI
                  ├─ should_send_message = true → Evolution sendText → INSERT gk_messages (outbound)
                  └─ should_send_message = false → só salva no DB
                Respond OK
```

#### Greeting Outbound — Fluxo
```
Cron 15min (Seg-Sex 9h-18h)
  → Checa horário comercial (BRT)
  → Checa daily cap (30/dia semana 1)
  → gk_get_pending_leads(5)
  → Tem leads?
      └─ SIM → SplitInBatches(1)
                  → Delay aleatório 60-120s
                  → Seleciona template aleatório + {clinic_name}
                  → Marca lead 'sent'
                  → Evolution sendText
                  → INSERT gk_conversations
                  → INSERT gk_messages (outbound)
                  → UPDATE gk_leads (sent_at, conversation_id)
```

#### Contrato FastAPI
- **Endpoint:** `POST https://ade.easyscale.co/v1/sdr/gatekeeper`
- **Header:** `X-API-Key: {FASTAPI_API_KEY}`
- **Request:**
  ```json
  {
    "clinic_name": "...",
    "clinic_phone": "5511999999999",
    "conversation_history": [{"role": "human"|"agent", "content": "..."}],
    "latest_message": "..."
  }
  ```
- **Response:**
  ```json
  {
    "response_message": "...",
    "should_send_message": true|false,
    "conversation_stage": "...",
    "extracted_manager_contact": "...",
    "extracted_manager_name": "..."
  }
  ```

#### Variáveis de Ambiente no Easypanel (n8n)
| Variável | Valor |
|---|---|
| `EVOLUTION_API_URL` | `https://evolution.easyscale.co` |
| `EVOLUTION_API_KEY` | `f331be59...` (chave da instância) |
| `EVOLUTION_INSTANCE_NAME` | `Sofia-EasyScale` |
| `FASTAPI_API_KEY` | chave do FastAPI |
| `N8N_API_KEY` | chave do n8n (para GitOps) |

#### Credencial no n8n
- **Nome:** `Postgres SDR Gatekeeper` — usada em todos os nodes Postgres dos 3 workflows

---

### Migrations (Supabase)

| Arquivo | Status |
|---|---|
| `001_create_conversations.sql` | ✅ Executada — cria `gk_conversations`, `gk_messages`, `gk_events` |
| `002_create_leads.sql` | ⚠️ **Pendente** — cria `gk_leads` + função `gk_get_pending_leads()` |
| `002_drop_status_constraint.sql` | ⚠️ **Pendente** — remove CHECK constraint do `status` (necessário para stages dinâmicos do FastAPI) |

---

### Bug Pendente — Reset Node

**Arquivo:** `workflows/sdr-gatekeeper-inbound.json`  
**Node:** `Evolution - Confirma Reset` (linha 124)

O node Postgres de DELETE não tem `RETURNING`, então `$json` chega vazio no node de envio. A referência atual está apontando para `$('Parse Evolution Payload')` — que é um node de outro ramo do fluxo e não está disponível neste contexto.

**Correção necessária** (linha 124):
```javascript
// DE (errado — Parse Evolution Payload não está disponível aqui):
"number": {{ JSON.stringify($('Parse Evolution Payload').first().json.remoteJid) }},

// PARA — referencia o node "É Reset?" que SIM está no ramo:
"number": {{ JSON.stringify($('É Reset?').first().json.remoteJid) }},
```

O mesmo vale para o node **`Respond - Reset OK`** (linha 138) que usa a mesma referência inválida:
```javascript
// DE:
$('Parse Evolution Payload').first().json.remoteJid

// PARA:
$('É Reset?').first().json.remoteJid
```

**Por que `$('É Reset?')` e não `$json`?**  
O node `Supabase - Reset Conversa` não retorna dados (DELETE sem RETURNING), então `$json` fica vazio. O node `É Reset?` é o último no ramo que tem os dados completos da mensagem original com `remoteJid`.

---

### Como Seguir

#### 1. Executar as migrations pendentes no Supabase
No SQL Editor do Supabase, rodar em ordem:
1. `supabase/migrations/002_drop_status_constraint.sql`
2. `supabase/migrations/002_create_leads.sql`

#### 2. Corrigir o Reset Node
Editar `workflows/sdr-gatekeeper-inbound.json` nos dois pontos acima, depois:
```bash
git add workflows/sdr-gatekeeper-inbound.json
git commit -m "fix: reset node usa \$('É Reset?') — Parse Evolution Payload não disponível no ramo"
git push
```
O GitOps deployer faz o deploy automático.

#### 3. Testar Reset
Enviar "reset" pelo WhatsApp → deve receber "Conversa resetada. Pode começar novamente."

#### 4. Testar Greeting
Inserir um lead na `gk_leads`:
```sql
INSERT INTO gk_leads (clinic_name, clinic_phone)
VALUES ('Clínica Teste', '5511982044215');
```
Aguardar o cron (próximos 15 min em horário comercial) ou disparar o workflow manualmente no n8n.

#### 5. Instância WhatsApp
- **Instância ativa:** `Sofia-EasyScale`
- **Webhook configurado:** `https://n8n.easyscale.co/webhook/sdr-gatekeeper-inbound`
- Já reconectada e funcionando ✅