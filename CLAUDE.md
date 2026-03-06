# AI Decision Engine — Contexto do Projeto

## Visão Geral

FastAPI com agentes DSPy que alimentam o SDR automatizado. Os agentes processam conversas WhatsApp de clínicas médicas, decidem respostas e classificam estágios da conversa.

**Repositório n8n (orquestração):** `/Users/jefersonalvarenga/Documents/easyscale-n8n-sdr-gatekeeper`

**URL de produção:** `https://ade.easyscale.co`

---

## Stack

- **FastAPI** — API HTTP
- **DSPy 2.6.13** — framework de otimização de prompts (LLM-agnóstico)
- **LangGraph** — grafos de agentes (`gatekeeper_graph`, `closer_graph`)
- **LLM configurável via `.env`:** `DSPY_PROVIDER` + `DSPY_MODEL`
  - **Atual (06/03/2026):** `DSPY_PROVIDER=anthropic` + `DSPY_MODEL=claude-haiku-4-5`
  - **Juiz de avaliação (fixo):** GPT-4o (`openai/gpt-4o`) — independente do modelo SDR
  - Histórico: Haiku, GPT-4o (ambos testados em benchmark), GLM5, xai/grok

---

## Agentes

### `app/agents/sdr/gatekeeper/`
**Objetivo:** conseguir o contato (WhatsApp ou email) do gestor/decisor da clínica, conversando com a recepção via WhatsApp.

**Signature:** `gatekeeper/signature.py` — prompt completo com:
- Estratégia em 4 etapas: confirmar clínica → pedir gestor → assunto comercial → agradecer
- Regra absoluta de ordem: "assunto comercial" SEMPRE antes de pitch ou Proposta Irrecusável
- Frases de "Proposta Irrecusável" (R$5k/mês em pacientes inativos, contato: Jeferson 11 98204-4215)
- 12 situações mapeadas (wait signal, success imediato, objection variants, failed)

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
do Supabase mas NÃO chegam no payload. Necessário para recovery inteligente pós-rejeição.

### `app/agents/sdr/closer/`
**Objetivo:** entrar em contato com o decisor capturado pelo Gatekeeper e agendar uma reunião/demo.

**Stages:** `greeting` → `presenting` → `objection_handling` → `scheduling` → `scheduled` / `lost`

**Inputs:**
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

## Infraestrutura de Testes

### Arquivos
```
app/agents/sdr/
  test_sdr_agents.py           # test runner principal (com juiz GPT-4o)
  test_gatekeeper_cases.json   # 49 cases, todos resolved (06/03/2026)
  test_closer_cases.json       # cases do closer
  optimize_gatekeeper.py       # BootstrapFewShot optimizer (ver seção abaixo)
  logs/                        # logs por execução: {timestamp}_{agent}_{provider}_{model}.log
artifacts/
  gatekeeper_optimized.json    # few-shot demos (gerado pelo optimizer)
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

### Mecanismo de avaliação
1. **Stage check** — `actual_stage == expected_stage`
2. **LLM Judge** (`_JudgeSignature` DSPy, via GPT-4o fixo) — avalia se a resposta segue a estratégia
3. **`resolved` tracking** — marca `true` no JSON quando passa, persiste entre runs

### Status dos cases (06/03/2026)
- **Gatekeeper: 49/49 resolved** (trajetória: 65% → 89% → 95% → 97.9% → 100%)
- Benchmark Haiku = GPT-4o = 65% (antes das correções de signature) — o bottleneck era o prompt
- 41 sintéticos + 8 reais (extraídos de `conversas-sdr.zip`: Tayná, Graciosa e outros)

---

## Optimizer (BootstrapFewShot)

### Como funciona
```bash
python -m app.agents.sdr.optimize_gatekeeper           # básico
python -m app.agents.sdr.optimize_gatekeeper --max-demos 6 --delay 1.5
python -m app.agents.sdr.optimize_gatekeeper --skip-validate  # só bootstrap
python -m app.agents.sdr.optimize_gatekeeper --warm-start     # continua do artifact atual
```

**Fluxo:**
1. Carrega 49 cases como trainset DSPy
2. Roda `BootstrapFewShot` → seleciona `max_demos` few-shot exemplares
3. Salva `artifacts/gatekeeper_optimized.json`
4. Valida todos os cases: se ≥90% → deploy; senão → abort

**Deploy automático:** `GatekeeperAgent.__init__` carrega o artifact automaticamente se ele existir
(desativar: `GatekeeperAgent(load_optimized=False)`)

### ⚠️ Problema conhecido (06/03/2026)
O BootstrapFewShot funcionou (6 demos selecionados, 19s), mas o artifact gerado causou **regressão 100% → 51%**.

Sintoma: respostas do tipo "Poderia repetir?" em quase todos os casos.

Causas prováveis:
- `rationale` vazio nos demos (ChainOfThought precisa do raciocínio preenchido)
- Demos com distribuição ruim: 4/6 são `handling_objection` (2 quase idênticos)
- DSPy 2.6.x pode ter incompatibilidade entre dict output do `forward()` e o schema de demos

**Status do artifact:** existe em `artifacts/gatekeeper_optimized.json` mas está causando regressão.
**Solução imediata:** deletar o artifact (`rm artifacts/gatekeeper_optimized.json`) para restaurar o comportamento base (100% nos cases).

**Próximos passos para o optimizer:**
- Investigar como popular o campo `rationale` nos demos
- Ou trocar para `dspy.Predict` (sem CoT) para simplificar o bootstrap
- Ou curar demos manualmente (selecionar os 6 melhores cases à mão)

---

## Conversas Reais de Referência

### Tayná — Padrão de Conversão (Jeferson)
```
Jeferson: "bom dia"
Tayná: "Bom dia, tudo bem com você?"
Jeferson: "com quem falo?"
Tayná: "Me chamo Tayná, sou a recepcionista da clínica"
Jeferson: "oi Tayná, aqui é Jeferson … eu gostaria de falar com o responsável da clínica"
Tayná: "No momento ele não se encontra. Gostaria de adiantar o assunto?"
Jeferson: "assunto comercial"
Tayná: "Entendi, vou repassar o contato dele ta"
```
**Padrão-chave:** abertura mínima → usa o nome → pedido direto → "assunto comercial" (2 palavras) → encerra

### Graciosa — Recovery Pós-Rejeição
```
Vera: "Bom dia, é da Clínica Graciosa?"
[...fluxo normal...]
Rebecka: "Sou sim, no momento, não estamos interessados, mas agradecemos🥰"
[1h depois]
Vera: "Agora que vi quem são vocês no detalhe. Nota 4.9, mais de 700 reviews e só 3 anúncios..."
```
**Padrão-chave:** rejeição suave → esperar → voltar com dado personalizado da clínica

---

## Pitch Atual vs. Desejado

**Pitch atual (no signature):**
> "recuperar em torno de R$5 mil por mês em pacientes inativos"

**Pitch desejado:**
> "Ajudamos clínicas a converter mais os leads que já chegam pelos anúncios"

**Mensagem de recovery pós-rejeição suave (padrão aprovado):**
```
4.9 com 700 avaliações — claramente fazem um bom trabalho!

Clínicas assim costumam perder em torno de 20% dos leads
no processo de atendimento, sem perceber.

Quer saber o número de vocês?
```
*(Requer dados de enriquecimento no payload para personalizar)*

---

## Configuração DSPy

`app/core/config.py` carrega `.env` automaticamente via `load_dotenv(override=True)` ao ser importado.
Isso resolve o problema de pydantic-settings não encontrar o `.env` quando rodando como módulo (`-m`).

```
DSPY_PROVIDER=anthropic      # ou openai, xai, glm, groq
DSPY_MODEL=claude-haiku-4-5  # ou gpt-4o, grok-4-1-fast-non-reasoning
```

---

## Ciclo de Melhoria Contínua (v2)

1. **Rodar testes sintéticos** — `test_sdr_agents.py --gatekeeper --all-cases`
2. **Mudar para homolog** → conversas chegam no WhatsApp do Jeferson
3. **Colar conversas reais boas** como novos cases no `test_gatekeeper_cases.json`
4. **Re-rodar optimizer** com `--warm-start` → artifact mais rico
5. **Verificar gate (≥90%)** antes de subir para produção
6. **Repetir** → confiança cresce gradualmente

---

## Pendências Conhecidas

- [ ] **URGENTE:** Deletar/corrigir `artifacts/gatekeeper_optimized.json` (causando regressão)
- [ ] Investigar optimizer: rationale vazio nos demos / opção de curar manualmente
- [ ] Adicionar `rating`, `reviews_count`, `ads_count`, `ads_group` nos inputs do Gatekeeper
- [ ] Atualizar pitch no `signature.py`: de "pacientes inativos" para "conversão de leads dos anúncios"
- [ ] Fluxo de recovery automático pós-rejeição suave (requer dados de enriquecimento)
- [ ] Approval queue no n8n: SDR gera → segura → Telegram notifica → Jeferson aprova/edita → envia
- [ ] Tirar cron do outbound (rodar na mão por ora)
