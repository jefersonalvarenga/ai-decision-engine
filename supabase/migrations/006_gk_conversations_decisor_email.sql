-- ============================================================================
-- Migration 006 — Adiciona decisor_email em gk_conversations (se não existir)
-- ============================================================================
-- Idempotente: usa IF NOT EXISTS

ALTER TABLE gk_conversations
  ADD COLUMN IF NOT EXISTS decisor_email VARCHAR(255);

COMMENT ON COLUMN gk_conversations.decisor_email IS
  'Email do decisor/gestor capturado pelo Gatekeeper (alternativa ao WhatsApp)';

-- Verificação
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name = 'gk_conversations' AND column_name = 'decisor_email';
