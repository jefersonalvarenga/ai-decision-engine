-- Migration 009: Adiciona remote_jid em gk_discovered_cases
-- remote_jid = JID WhatsApp da clínica (ex: 5511999999999@s.whatsapp.net)
-- Necessário para rastrear qual clínica gerou cada descoberta

ALTER TABLE gk_discovered_cases
  ADD COLUMN IF NOT EXISTS remote_jid TEXT;

CREATE INDEX IF NOT EXISTS idx_gk_discovered_cases_remote_jid
  ON gk_discovered_cases(remote_jid)
  WHERE remote_jid IS NOT NULL;

-- Grant para n8n_gatekeeper (padrão do projeto)
GRANT ALL ON TABLE gk_discovered_cases TO n8n_gatekeeper;
