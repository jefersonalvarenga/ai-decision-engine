-- ============================================================================
-- Migration 005 — Tabela de configuração do pipeline SDR
-- ============================================================================
--
-- Cria a tabela sdr_config com uma única linha que controla o modo de operação:
--
--   'homolog'    → pick_next_clinic() substitui out_clinic_phone pelo número de
--                  homologação — pipeline inteiro roda com dados reais, mas as
--                  mensagens WhatsApp chegam em um número controlado da equipe
--
--   'production' → comportamento 100% normal, sem nenhuma substituição
--
-- Troca de modo (sem deploy):
--   UPDATE sdr_config SET environment = 'production' WHERE id = 1;
--   UPDATE sdr_config SET environment = 'homolog'    WHERE id = 1;
--
-- EXECUTAR NO SUPABASE SQL EDITOR.
-- ============================================================================

CREATE TABLE IF NOT EXISTS sdr_config (
    id            SERIAL PRIMARY KEY,
    environment   VARCHAR(20) NOT NULL DEFAULT 'homolog',
    homolog_phone VARCHAR(30) DEFAULT '5511933752363',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Linha única de configuração (inicializa em modo homolog)
INSERT INTO sdr_config (id, environment, homolog_phone)
VALUES (1, 'homolog', '5511933752363')
ON CONFLICT (id) DO NOTHING;

-- Grants
GRANT SELECT ON sdr_config TO anon;
GRANT ALL ON sdr_config TO service_role;

-- Verificação
SELECT id, environment, homolog_phone, created_at FROM sdr_config;
