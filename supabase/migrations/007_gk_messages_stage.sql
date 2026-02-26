-- ============================================================================
-- Migration 007 — Adiciona coluna stage em gk_messages
-- ============================================================================
-- Permite rastrear o stage do agente (opening, requesting, handling_objection,
-- success, failed) por turno, eliminando a heurística de contagem de objeções.

ALTER TABLE gk_messages
  ADD COLUMN IF NOT EXISTS stage VARCHAR(50);

COMMENT ON COLUMN gk_messages.stage IS
  'Stage interno do GatekeeperAgent ao gerar esta mensagem: opening | requesting | handling_objection | success | failed. NULL para mensagens inbound (recepção).';

-- Verificação
-- SELECT direction, stage, content FROM gk_messages ORDER BY created_at DESC LIMIT 10;
