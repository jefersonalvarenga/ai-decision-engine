-- ============================================================================
-- SDR Pipeline Schema
-- ============================================================================
-- Tabelas centrais do pipeline SDR que conectam Gatekeeper → Closer.
--
-- FLUXO:
--   pick_next_clinic() → gk_leads → [Gatekeeper] → clinic_decisors
--   clinic_decisors → closer_conversations + closer_messages → [Closer]
--   Closer 'scheduled' → clinic_decisors.status = 'scheduled'
--   pick_next_clinic() usa clinic_decisors para medir conversões por grupo
--
-- EXECUTAR NO SQL EDITOR DO SUPABASE em ordem.
-- ============================================================================


-- ============================================================================
-- FUNÇÃO AUXILIAR: updated_at automático
-- (Reutilizada por todas as tabelas com trigger)
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- TABELA 1: clinic_decisors
-- Gestores de clínicas capturados pelo Gatekeeper.
-- Ponto de entrada para o Closer e fonte de dados para o bandit (pick_next_clinic).
-- ============================================================================
CREATE TABLE IF NOT EXISTS clinic_decisors (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Origem — link com Google Maps e Gatekeeper
    place_id            TEXT,           -- FK lógica → google_maps_signals.place_id
    gk_conversation_id  UUID,           -- FK lógica → gk_conversations.id

    -- Clínica (recepção)
    clinic_name         VARCHAR(255) NOT NULL,
    clinic_phone        VARCHAR(50)  NOT NULL,   -- Telefone da clínica/recepção

    -- Gestor capturado pelo Gatekeeper
    manager_name        VARCHAR(255),
    manager_phone       VARCHAR(50),             -- WhatsApp direto do gestor
    manager_email       VARCHAR(255),

    -- Dados do scrap (contexto para o Closer e para o bandit)
    clinic_specialty    VARCHAR(100),            -- 'odonto', 'estética', 'dermatologia', etc.
    google_rating       NUMERIC(3,1),
    google_reviews      INT,
    google_ads_count    INT,
    lead_score          NUMERIC(5,2),
    ads_group           VARCHAR(20),             -- 'ads_high' | 'ads_mid' | 'ads_low'

    -- Status do pipeline SDR completo (controlado pelo Closer após 'captured')
    status              VARCHAR(30) NOT NULL DEFAULT 'captured',
    -- 'captured'         → gestor obtido pelo GK, aguardando Closer
    -- 'greeted'          → Closer enviou primeira mensagem
    -- 'initial_approach' → conversa iniciada
    -- 'proposal_offered' → proposta apresentada
    -- 'negotiating'      → em negociação
    -- 'scheduled'        → reunião agendada ✅
    -- 'success'          → cliente comprou 🎉
    -- 'lost'             → recusou definitivamente
    -- 'no_show'          → não compareceu à reunião

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_clinic_decisors_status
    ON clinic_decisors(status);

CREATE INDEX IF NOT EXISTS idx_clinic_decisors_place_id
    ON clinic_decisors(place_id);

CREATE INDEX IF NOT EXISTS idx_clinic_decisors_clinic_phone
    ON clinic_decisors(clinic_phone);

-- Garante que o mesmo gestor (por WhatsApp) não seja abordado duas vezes
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinic_decisors_manager_phone
    ON clinic_decisors(manager_phone)
    WHERE manager_phone IS NOT NULL;

-- Trigger para updated_at
CREATE TRIGGER trg_clinic_decisors_updated_at
BEFORE UPDATE ON clinic_decisors
FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================================
-- TABELA 2: closer_conversations
-- Sessões do Closer com gestores (análoga a gk_conversations para o Gatekeeper).
-- ============================================================================
CREATE TABLE IF NOT EXISTS closer_conversations (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Vínculo com o pipeline
    clinic_decisor_id   UUID REFERENCES clinic_decisors(id) ON DELETE CASCADE,
    manager_phone       VARCHAR(50)  NOT NULL,
    remote_jid          VARCHAR(60)  GENERATED ALWAYS AS (manager_phone || '@s.whatsapp.net') STORED,

    -- Contexto passado ao Closer
    clinic_name         VARCHAR(255) NOT NULL,
    clinic_specialty    VARCHAR(100),
    manager_name        VARCHAR(255),

    -- Estado da conversa
    status              VARCHAR(30)  NOT NULL DEFAULT 'active',
    -- 'active'     → em andamento
    -- 'scheduled'  → reunião confirmada ✅
    -- 'lost'       → perdido
    -- 'stalled'    → sem resposta por 24h (reativa se gestor responder)
    -- 'expired'    → sem resposta por 48h

    -- Resultado (preenchido quando status = 'scheduled')
    meeting_datetime    TIMESTAMPTZ,
    meeting_confirmed   BOOLEAN DEFAULT FALSE,

    -- Controle de tentativas e tempo
    message_count       INT DEFAULT 0,
    attempt_count       INT DEFAULT 0,          -- Apenas mensagens do agente
    evolution_instance  VARCHAR(100),
    last_message_at     TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '48 hours'),

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_closer_conv_manager_phone
    ON closer_conversations(manager_phone);

CREATE INDEX IF NOT EXISTS idx_closer_conv_status
    ON closer_conversations(status);

CREATE INDEX IF NOT EXISTS idx_closer_conv_clinic_decisor
    ON closer_conversations(clinic_decisor_id);

CREATE INDEX IF NOT EXISTS idx_closer_conv_expires
    ON closer_conversations(expires_at)
    WHERE status = 'active';

-- Trigger para updated_at
CREATE TRIGGER trg_closer_conversations_updated_at
BEFORE UPDATE ON closer_conversations
FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================================
-- TABELA 3: closer_messages
-- Histórico de mensagens do Closer (análoga a gk_messages).
-- ============================================================================
CREATE TABLE IF NOT EXISTS closer_messages (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id     UUID REFERENCES closer_conversations(id) ON DELETE CASCADE,

    direction           VARCHAR(10)  NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    content             TEXT         NOT NULL,
    message_type        VARCHAR(20)  DEFAULT 'text',
    wamid               VARCHAR(255),
    agent_stage         VARCHAR(30),             -- Stage do Closer ao enviar esta mensagem

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_closer_messages_conv
    ON closer_messages(conversation_id, created_at);


-- ============================================================================
-- GRANTS (para o role que o n8n usa)
-- ============================================================================
GRANT ALL ON clinic_decisors         TO service_role;
GRANT ALL ON closer_conversations    TO service_role;
GRANT ALL ON closer_messages         TO service_role;

GRANT SELECT, INSERT, UPDATE ON clinic_decisors        TO anon;
GRANT SELECT, INSERT, UPDATE ON closer_conversations   TO anon;
GRANT SELECT, INSERT         ON closer_messages        TO anon;
