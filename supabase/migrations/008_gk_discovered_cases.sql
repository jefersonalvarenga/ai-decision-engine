-- Migration 008: Tabela de descobertas de conversas reais
-- Alimentada pelo GLM ao final de cada conversa (rawStage = failed | success)
-- Usada para gerar novos casos de teste automaticamente

CREATE TABLE IF NOT EXISTS gk_discovered_cases (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id         UUID REFERENCES gk_conversations(id) ON DELETE SET NULL,
  clinic_name             TEXT,
  final_stage             VARCHAR(50),           -- "failed" | "success"
  quality_score           NUMERIC(3,2),          -- 0.00 a 1.00
  outcome_label           VARCHAR(50),           -- SUCCESS | EMAIL_SUCCESS | GRACEFUL_DENIED | SLOW_EXIT | STUCK | BLOCKED_RISK
  outcome_reason          TEXT,
  sofia_did_well          JSONB DEFAULT '[]',    -- lista de pontos positivos
  sofia_should_improve    JSONB DEFAULT '[]',    -- lista de melhorias
  is_new_pattern          BOOLEAN DEFAULT FALSE, -- padrão não coberto pelos 6 cenários
  suggested_scenario_name TEXT,                  -- nome sugerido se is_new_pattern = true
  full_conversation       TEXT,                  -- histórico completo formatado
  raw_glm_response        TEXT,                  -- resposta bruta do GLM para debug
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gk_discovered_cases_conversation
  ON gk_discovered_cases(conversation_id);

CREATE INDEX IF NOT EXISTS idx_gk_discovered_cases_outcome
  ON gk_discovered_cases(outcome_label);

CREATE INDEX IF NOT EXISTS idx_gk_discovered_cases_new_pattern
  ON gk_discovered_cases(is_new_pattern) WHERE is_new_pattern = TRUE;

COMMENT ON TABLE gk_discovered_cases IS
  'Avaliações automáticas de conversas reais pelo GLM. '
  'Fonte de novos casos de teste para o pipeline de auto-tuning.';

-- Grants — cobre todos os roles que Supabase/n8n pode usar
-- (postgres = owner via SQL Editor, service_role = pooler, anon/authenticated/authenticator = PostgREST)
-- (n8n_gatekeeper = role customizado usado pela credential Postgres do n8n)
ALTER TABLE gk_discovered_cases OWNER TO postgres;
GRANT ALL ON TABLE gk_discovered_cases TO postgres;
GRANT ALL ON TABLE gk_discovered_cases TO service_role;
GRANT ALL ON TABLE gk_discovered_cases TO anon;
GRANT ALL ON TABLE gk_discovered_cases TO authenticated;
GRANT ALL ON TABLE gk_discovered_cases TO authenticator;
GRANT ALL ON TABLE gk_discovered_cases TO n8n_gatekeeper;

-- Garante que tabelas futuras criadas pelo postgres já nasçam com grant para n8n_gatekeeper
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO n8n_gatekeeper;

NOTIFY pgrst, 'reload schema';
