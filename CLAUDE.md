# AI Decision Engine — Contexto do Projeto

## Visão Geral

FastAPI com agentes DSPy que alimentam o SDR automatizado. Os agentes processam conversas WhatsApp de clínicas médicas, decidem respostas e classificam estágios da conversa.

**Repositório n8n (orquestração):** `/Users/jefersonalvarenga/Documents/easyscale-n8n-sdr-gatekeeper`

**URL de produção:** `https://ade.easyscale.co`

---

## Stack

- **FastAPI** — API HTTP
- **DSPy** — framework de otimização de prompts (LLM-agnóstico)
- **LangGraph** — grafos de agentes (`gatekeeper_graph`, `closer_graph`)
- **LLM configurável via `.env`:** `DSPY_PROVIDER` + `DSPY_MODEL`
  - Produção atual: GLM5 (`glm` provider)
  - Testes históricos: GPT-4o (`openai` provider)
  - Candidato a substituição: Claude API (melhor em português BR e raciocínio contextual)

---

## Agentes

### `app/agents/sdr/gatekeeper/`
**Objetivo:** conseguir o contato (WhatsApp ou email) do gestor/decisor da clínica, conversando com a recepção via WhatsApp.

**Signature:** `gatekeeper/signature.py` — prompt completo e detalhado com:
- Estratégia comprovada (4 etapas: confirmar clínica → pedir gestor → assunto comercial → agradecer)
- Frases de "Proposta Irrecusável" (R$5k/mês em pacientes inativos, contato: Jeferson 11 98204-4215)
- Regras de classificação de stage
- Situações de espera (should_continue=false sem mensagem)

**Stages:**
- `opening` → primeira mensagem confirmando a clínica
- `requesting` → pedindo contato do gestor
- `handling_objection` → recepção criou obstáculo (máx 3x)
- `success` → contato obtido (phone ou email)
- `failed` → encerrou sem contato

**Inputs do gatekeeper:**
```python
clinic_name, sdr_name, conversation_history, latest_message,
current_hour, current_weekday, attempt_count
```

⚠️ **GAP CRÍTICO:** não recebe dados de enriquecimento da clínica.
Os campos `rating`, `reviews_count`, `ads_count` existem na tabela `google_maps_signals`
do Supabase mas NÃO chegam no payload. Necessário para recovery inteligente pós-rejeição
(ex: "4.9, 700 reviews, só 3 anúncios — clínicas assim perdem 20% dos leads...").

### `app/agents/sdr/closer/`
**Objetivo:** entrar em contato com o decisor capturado pelo Gatekeeper e agendar uma reunião/demo.

**Stages:**
- `greeting` → primeira mensagem ao gestor
- `presenting` → apresentando proposta
- `objection_handling` → tratando objeções
- `scheduling` → agendando horário
- `scheduled` → reunião confirmada
- `lost` → não foi possível agendar

**Inputs do closer:**
```python
manager_name, manager_phone, clinic_name, clinic_specialty,
conversation_history, latest_message, available_slots,
current_hour, attempt_count
```

Suporte a múltiplas mensagens: separadas por `|||` em `response_message`.

### `app/agents/reengage/`
Multi-agente para reengajamento: analyst → strategist → copywriter → critic.

### `app/agents/router/`
Roteador de intenção (identifica tipo de mensagem/pedido).

---

## Pitch Atual vs. Desejado

**Pitch atual (no signature):**
> "recuperar em torno de R$5 mil por mês em pacientes inativos"

**Pitch novo desejado (decisão desta sessão):**
> "Ajudamos clínicas a converter mais os leads que já chegam pelos anúncios"

**Raciocínio:** clínicas com boa reputação (ex: 4.9 rating, 700 reviews) já têm demanda.
O problema não é crescer do zero, é não perder o que já está chegando pelos anúncios.
"Você já está pagando pelos anúncios — a gente aumenta quantos desses leads viram clientes."

**Mensagem de recovery pós-rejeição suave (padrão aprovado):**
```
4.9 com 700 avaliações — claramente fazem um bom trabalho!

Clínicas assim costumam perder em torno de 20% dos leads
no processo de atendimento, sem perceber.

Quer saber o número de vocês?
```
*(Requer dados de enriquecimento no payload para personalizar)*

---

## Infraestrutura de Testes

### Arquivos
- `test_sdr_agents.py` — test runner principal
- `test_gatekeeper_cases.json` — 41 casos (5 resolved em 27/02/2026)
- `test_closer_cases.json` — casos do closer
- `logs/` — logs por execução (`{timestamp}_{agent}_{provider}_{model}.log`)

### Como rodar
```bash
cd /Users/jefersonalvarenga/Documents/ai-decision-engine
python -m app.agents.sdr.test_sdr_agents --gatekeeper          # próximos pendentes
python -m app.agents.sdr.test_sdr_agents --gatekeeper --n 1    # só 1 caso
python -m app.agents.sdr.test_sdr_agents --gatekeeper --case 3 # caso específico
python -m app.agents.sdr.test_sdr_agents --interactive          # modo interativo
```

### Mecanismo de avaliação
1. **Stage check** — `actual_stage == expected_stage`
2. **LLM Judge** (`_JudgeSignature` DSPy) — avalia se a resposta segue a estratégia
3. **`resolved` tracking** — marca `true` no JSON quando passa, persiste entre runs

### Status atual dos cases (05/03/2026)
- Gatekeeper: 5/41 resolved, 36 pendentes
- Casos reais a adicionar: conversa Tayná (Jeferson → conversão), conversa Graciosa (recovery pós-rejeição)

---

## Conversas Reais de Referência

### Tayná — Padrão de Conversão (Jeferson)
```
Jeferson: "bom dia"
Tayná: "Bom dia, tudo bem com você?"
Jeferson: "com quem falo?"
Tayná: "Me chamo Tayná, sou a recepcionista da clínica"
Jeferson: "oi Tayná, aqui é Jeferson … tudo bem e você? eu gostaria de falar com o responsável da clínica"
Tayná: "No momento ele não se encontra. Gostaria de adiantar o assunto?"
Jeferson: "assunto comercial"
Tayná: "Entendi, vou repassar o contato dele ta"
```
**Padrão-chave:** abertura mínima → pergunta o nome → usa o nome → pedido direto → "assunto comercial" (2 palavras) → encerra

### Graciosa — Recovery Pós-Rejeição
```
Vera: "Bom dia, é da Clínica Graciosa?"
[...fluxo normal...]
Vera: "Ajudamos clínicas a aumentar o faturamento, você seria a responsável?"
Rebecka: "Sou sim, no momento, não estamos interessados, mas agradecemos🥰"
[1h depois]
Vera: "Agora que vi quem são vocês no detalhe. Nota 4.9, mais de 700 reviews e só 3 anúncios..."
```
**Padrão-chave:** rejeição suave → esperar → voltar com dado personalizado da clínica → ângulo de "dinheiro deixado na mesa"

---

## Configuração DSPy

```python
# app/core/config.py
DSPY_PROVIDER = "glm"  # ou "openai", "anthropic"
DSPY_MODEL = "glm-5"   # ou "gpt-4o", "claude-sonnet-4-5" etc.
```

Para trocar de GLM5 para Claude API: alterar `.env` e rodar os 36 casos pendentes como benchmark comparativo.

---

## Pendências Conhecidas

- [ ] Adicionar `rating`, `reviews_count`, `ads_count`, `ads_group` nos inputs do Gatekeeper
- [ ] Atualizar pitch no `signature.py`: de "pacientes inativos" para "conversão de leads dos anúncios"
- [ ] Adicionar cases reais (Tayná, Graciosa) ao `test_gatekeeper_cases.json`
- [ ] Rodar os 36 cases pendentes do gatekeeper
- [ ] Benchmark GLM5 vs Claude API usando os cases como referência
- [ ] Fluxo de recovery automático pós-rejeição suave (requer dados de enriquecimento no payload)
