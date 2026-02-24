-- ============================================================================
-- Migration 004 — Alinhamento de status do pipeline SDR
-- ============================================================================
--
-- Contexto:
--   Os status das tabelas gk_leads e gk_conversations foram redesenhados para
--   refletir melhor o funil de negócio e separar responsabilidades:
--
--   gk_leads (milestones de negócio):
--     'pending'  → 'created'            (lead selecionado pelo bandit)
--     'sent'     → 'gathering_decisor'  (greeting enviado, conversa ativa)
--     (decisor_captured: novo estado — setado pelo inbound quando GK captura gestor)
--
--   gk_conversations (estados da sessão do Gatekeeper):
--     'active'   → 'greeting_sent'      (conversa criada pelo greeting workflow)
--     'active'   → 'gathering_decisor'  (conversa criada por inbound orgânico)
--     (stalled reativado → 'gathering_decisor' em vez de 'active')
--
-- EXECUTAR NO SUPABASE SQL EDITOR após deploy dos workflows.
-- ============================================================================

-- gk_leads: 'pending' → 'created'
UPDATE gk_leads
SET status = 'created', updated_at = NOW()
WHERE status = 'pending';

-- gk_leads: 'sent' → 'gathering_decisor'
-- (leads que já receberam greeting e estão com conversa ativa)
UPDATE gk_leads
SET status = 'gathering_decisor', updated_at = NOW()
WHERE status = 'sent';

-- gk_conversations: 'active' → 'greeting_sent'
-- (conversas criadas pelo greeting workflow — aguardando primeira resposta)
-- Identifica pela presença de clinic_name (greeting preenche, inbound orgânico não preenche)
UPDATE gk_conversations
SET status = 'greeting_sent', updated_at = NOW()
WHERE status = 'active'
  AND clinic_name IS NOT NULL
  AND clinic_name != '';

-- gk_conversations: 'active' → 'gathering_decisor'
-- (conversas criadas por inbound orgânico, sem clinic_name)
UPDATE gk_conversations
SET status = 'gathering_decisor', updated_at = NOW()
WHERE status = 'active';

-- ============================================================================
-- Verificação (executar após a migration)
-- ============================================================================
-- SELECT status, COUNT(*) FROM gk_leads GROUP BY status ORDER BY status;
-- SELECT status, COUNT(*) FROM gk_conversations GROUP BY status ORDER BY status;
