# AI Decision Engine — Contexto do Projeto

## Visão Geral

FastAPI com agentes DSPy que alimentam o SDR automatizado. Os agentes processam conversas WhatsApp de clínicas médicas, decidem respostas e classificam estágios da conversa.

**Repositório n8n (orquestração):** `/Users/jefersonalvarenga/Documents/easyscale-n8n-sdr-gatekeeper`

**URL de produção:** `https://ade.easyscale.co`

---

## Stack

- **FastAPI** — API HTTP stateless
- **DSPy 2.6.13** — framework de otimização de prompts (LLM-agnóstico)
- **LangGraph** — grafos de agentes (`gatekeeper_graph`, `closer_graph`)
- **LLM configurável via EasyPanel (produção) ou `.env` (local):**
  - `DSPY_PROVIDER=anthropic` + `DSPY_MODEL=claude-haiku-4-5` (atual)
  - Juiz de avaliação (fixo): GPT-4o (`openai/gpt-4o`)
  - EasyPanel env vars têm prioridade sobre `.env` (`override=False` em `config.py`)

---

## Arquitetura

- FastAPI é **stateless** — não acessa Supabase diretamente (exceto `gk_logs`: fire-and-forget via httpx)
- n8n é responsável por: persistência, histórico, envio de mensagens, leitura de config
- n8n envia todos os dados necessários no payload para o FastAPI

---

## Agentes

### `app/agents/sdr/gatekeeper/`
**Objetivo:** conseguir o contato (WhatsApp ou email) do gestor/decisor da clínica, conversando com a recepção via WhatsApp.

**Princípio:** zero determinismo — todo comportamento passa pelo LLM. Sem scripts, sem if/else de lógica de negócio.

**Signature:** `gatekeeper/signature.py` (~130 linhas) — princípios de SDR humano:
- Vera é mulher, SDR da EasyScale
- 5 táticas: `direct | feedback | referral | social_proof | data_hook`
- Análise do estado da conversa antes de cada resposta
- Progressão quando pressionada: "assunto comercial" → "atendimento da clínica" → pivote para canal
- Máx 2 frases por mensagem; nunca repete pedido com as mesmas palavras

**Stages:**
- `requesting` → pedindo contato do gestor
- `handling_objection` → recepção criou obstáculo
- `success` → contato obtido (phone ou email)
- `failed` → encerrou sem contato

**Inputs:**
```python
clinic_name, sdr_name, conversation_history, latest_message,
current_hour, current_weekday, detected_persona
```

**OutputFields:** `response_message, should_send_message, conversation_stage, approach_used,
extracted_manager_contact, extracted_manager_email, extracted_manager_name`

**Grafo (`gatekeeper_graph`):**
- `detect_persona` → roda SEMPRE a cada turno (PersonaDetector via LLM)
- `process` → GatekeeperAgent — todas as personas exceto menu_bot
- `process_menu_bot` → MenuBotAgent — apenas menu_bot
- Campo `_node_executed` propagado no resultado → `gk_logs.node_executed`

⚠️ **GAP pendente:** dados de enriquecimento (`google_rating`, `google_reviews`, `google_ads_count`) existem em `gk_leads` mas ainda não chegam no payload FastAPI.

### `app/agents/sdr/closer/`
**Objetivo:** contatar o decisor capturado pelo Gatekeeper e agendar reunião/demo.

**Stages:** `greeting` → `presenting` → `objection_handling` → `scheduling` → `scheduled` / `lost`

**Inputs:** `manager_name, manager_phone, clinic_name, clinic_specialty, conversation_history, latest_message, available_slots, current_hour, attempt_count`

Suporte a múltiplas mensagens: separadas por `|||` em `response_message`.

### `app/agents/reengage/`
Multi-agente para reengajamento: analyst → strategist → copywriter → critic.

### `app/agents/router/`
Roteador de intenção (identifica tipo de mensagem/pedido).

---

## Infraestrutura de Testes

```
app/agents/sdr/
  test_sdr_agents.py           # test runner (juiz GPT-4o)
  test_gatekeeper_cases.json   # 49 cases, todos resolved
  test_closer_cases.json       # cases do closer
  optimize_gatekeeper.py       # BootstrapFewShot optimizer
  logs/                        # {timestamp}_{agent}_{provider}_{model}.log
artifacts/
  gatekeeper_optimized.json    # few-shot demos (se existir, carregado automaticamente)
```

### Como rodar testes
```bash
cd /Users/jefersonalvarenga/Documents/ai-decision-engine
python -m app.agents.sdr.test_sdr_agents --gatekeeper            # pendentes
python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases # todos
python -m app.agents.sdr.test_sdr_agents --gatekeeper --n 1       # só 1 caso
python -m app.agents.sdr.test_sdr_agents --gatekeeper --case 3    # caso específico
python -m app.agents.sdr.test_sdr_agents --interactive            # modo interativo
```

### Status dos cases
- **Gatekeeper: 49/49 resolved** — 41 sintéticos + 8 reais (Tayná, Graciosa e outros)
- Benchmark: Haiku = GPT-4o = 65% antes das correções de signature (bottleneck era o prompt)

---

## Optimizer (BootstrapFewShot)

```bash
python -m app.agents.sdr.optimize_gatekeeper
python -m app.agents.sdr.optimize_gatekeeper --max-demos 6 --delay 1.5
python -m app.agents.sdr.optimize_gatekeeper --skip-validate
python -m app.agents.sdr.optimize_gatekeeper --warm-start
```

**Deploy automático:** `GatekeeperAgent.__init__` carrega `artifacts/gatekeeper_optimized.json` se existir.
Para desativar: `GatekeeperAgent(load_optimized=False)`

⚠️ **Problema conhecido:** artifact gerado causou regressão 100% → 51% (rationale vazio nos demos + distribuição ruim). Se houver regressão, deletar o artifact para restaurar comportamento base.

---

## Homolog — Como Funciona

- Outbound salva `remote_jid = JID do Jeferson` (`5511982044215@s.whatsapp.net`) em `gk_conversations`
- `ON CONFLICT (remote_jid)` → uma conversa homolog ativa por vez
- Inbound busca por `remote_jid = remoteJid` direto — sem lógica especial de homolog
- `clinic_name` real preservado na conversa; envio redirecionado para WhatsApp do Jeferson via Roteamento Homolog
- **Reset:** enviar "reset" no WhatsApp → nó `É Reset?` detecta → `Supabase - Reset Conversa` deleta tudo `is_homolog=true`

---

## Workflow n8n — Inbound (estado atual)

```
Parse Evolution Payload → É Operador? → É Reset? →
  [reset] → Supabase - Reset Conversa
  [não]   → Supabase Lê Config →
            Supabase - Busca Conversa (JOIN por remote_jid) →
            Merge - Contexto da Conversa →
            Supabase - Salva Inbound e Busca Histórico →
            Verifica Bloqueios → Prepara Payload FastAPI →
            HTTP - FastAPI Gatekeeper → Processa Resposta FastAPI →
            Supabase Verifica Wamid Pós-FastAPI →
              [válido] → Deve Enviar? →
                [sim] → Roteamento Homolog → Evolution API →
                        Supabase Atualiza Status + Salva Msg Outbound + Salva Evento
                [não] → Supabase Atualiza Status
```

**Nó `save-inbound-and-fetch-history`:** histórico inclui `outbound` e `inbound` via `(m.wamid IS NULL OR m.wamid <> wamid_atual)`.

---

## Tabelas Supabase Relevantes

- `gk_conversations` — conversas ativas (`remote_jid`, `clinic_name`, `is_homolog`, `detected_persona`)
- `gk_messages` — histórico (`direction`, `content`, `stage`, `wamid`)
- `gk_leads` — fila de prospecção (`approaches_tried jsonb`, `final_stage`, `google_rating`, `google_reviews`, `google_ads_count`)
- `gk_logs` — log por request (`approach_used`, `node_executed`, `reasoning`, `processing_time_ms`)
- `sdr_debounce` — dedup por `wamid`
- `sdr_config` — config global (`sdr_name`, `environment`, `homolog_phone`)

---

## Conversas Reais de Referência

### Tayná — Padrão de Conversão
**Padrão-chave:** abertura mínima → usa o nome → pedido direto → "assunto comercial" (2 palavras) → encerra

### Graciosa — Recovery Pós-Rejeição
**Padrão-chave:** rejeição suave → esperar → voltar com dado personalizado da clínica
```
"4.9 com 700 avaliações — claramente fazem um bom trabalho!
Clínicas assim costumam perder em torno de 20% dos leads no processo de atendimento, sem perceber.
Quer saber o número de vocês?"
```
*(Requer dados de enriquecimento no payload)*

---

## Pitch

**Atual (no signature):** "recuperar em torno de R$5 mil por mês em pacientes inativos"

**Desejado:** "Ajudamos clínicas a converter mais os leads que já chegam pelos anúncios"

---

## Ciclo de Melhoria Contínua

1. Rodar testes sintéticos — `test_sdr_agents.py --gatekeeper --all-cases`
2. Mudar para homolog → conversar via WhatsApp do Jeferson
3. Colar conversas reais boas como novos cases no JSON
4. Re-rodar optimizer com `--warm-start`
5. Verificar gate (≥90%) antes de subir para produção
6. Repetir

---

## Pendências Conhecidas

- [ ] Pitch no `signature.py`: "pacientes inativos" → "conversão de leads dos anúncios"
- [ ] Dados de enriquecimento (`google_rating` etc.) chegar no payload FastAPI → agent usar em recovery
- [ ] Fluxo de recovery automático pós-rejeição suave
- [ ] Approval queue no n8n: SDR gera → Telegram notifica → Jeferson aprova/edita → envia
- [ ] Investigar optimizer: rationale vazio nos demos / curar manualmente
- [ ] Rodar `python -m app.agents.sdr.test_sdr_agents --gatekeeper --all-cases`
