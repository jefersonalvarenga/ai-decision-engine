-- ============================================================================
-- Migration 003: Renomear sdr_contacts → clinic_decisors
--               Adicionar campos place_id/lead_score/ads_group em gk_leads
-- ============================================================================
--
-- EXECUTAR NO SQL EDITOR DO SUPABASE em ordem.
-- Idempotente: usa IF NOT EXISTS / IF EXISTS onde possível.
--
-- DEPENDÊNCIAS: sdr_schema.sql (001/002 já executados)
-- ============================================================================


-- ============================================================================
-- PARTE 1: Adicionar colunas em gk_leads para fechar o loop do bandit
-- ============================================================================

ALTER TABLE gk_leads
  ADD COLUMN IF NOT EXISTS place_id   TEXT,
  ADD COLUMN IF NOT EXISTS lead_score NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS ads_group  VARCHAR(20);

COMMENT ON COLUMN gk_leads.place_id   IS 'FK lógica → google_maps_signals.place_id (via pick_next_clinic)';
COMMENT ON COLUMN gk_leads.lead_score IS 'Score calculado por pick_next_clinic() no momento da seleção';
COMMENT ON COLUMN gk_leads.ads_group  IS 'ads_high | ads_mid | ads_low — arm do bandit';


-- ============================================================================
-- PARTE 2: Renomear sdr_contacts → clinic_decisors
-- ============================================================================

-- Renomear tabela principal
ALTER TABLE sdr_contacts RENAME TO clinic_decisors;

-- Renomear índices (PostgreSQL preserva os índices, mas os nomes ficam obsoletos)
ALTER INDEX IF EXISTS idx_sdr_contacts_status        RENAME TO idx_clinic_decisors_status;
ALTER INDEX IF EXISTS idx_sdr_contacts_place_id      RENAME TO idx_clinic_decisors_place_id;
ALTER INDEX IF EXISTS idx_sdr_contacts_clinic_phone  RENAME TO idx_clinic_decisors_clinic_phone;
ALTER INDEX IF EXISTS idx_sdr_contacts_manager_phone RENAME TO idx_clinic_decisors_manager_phone;

-- Renomear trigger
ALTER TRIGGER trg_sdr_contacts_updated_at ON clinic_decisors
  RENAME TO trg_clinic_decisors_updated_at;

-- Renomear FK em closer_conversations (sdr_contact_id → clinic_decisor_id)
ALTER TABLE closer_conversations
  RENAME COLUMN sdr_contact_id TO clinic_decisor_id;

-- Atualizar índice da FK em closer_conversations
ALTER INDEX IF EXISTS idx_closer_conv_sdr_contact
  RENAME TO idx_closer_conv_clinic_decisor;

-- Atualizar GRANTs para novo nome
GRANT ALL ON clinic_decisors TO service_role;
GRANT SELECT, INSERT, UPDATE ON clinic_decisors TO anon;


-- ============================================================================
-- PARTE 3: Recriar pick_next_clinic() com referência corrigida
-- (sdr_contacts → clinic_decisors)
-- ============================================================================
-- Colar aqui o conteúdo atualizado do arquivo pick_next_clinic.sql
-- (será executado pelo script de deploy após o rename acima)
