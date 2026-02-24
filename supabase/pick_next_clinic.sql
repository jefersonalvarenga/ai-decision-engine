-- ============================================================================
-- pick_next_clinic() — Epsilon-Greedy Multi-Armed Bandit
-- ============================================================================
--
-- Seleciona a próxima clínica para abordagem SDR de forma inteligente.
--
-- GRUPOS (arms do bandit):
--   ads_high → ads_count >= 5  (investe pesado em marketing)
--   ads_mid  → ads_count 2-4   (investe moderado)
--   ads_low  → ads_count = 1   (investe pouco)
--
-- ALGORITMO:
--   epsilon = max(0.2, 1 - total_conversions/50)
--
--   EXPLORE (epsilon % do tempo):
--     Sorteia grupo uniformemente — garante cobertura de todos os segmentos
--
--   EXPLOIT (1-epsilon % do tempo):
--     Sorteia grupo com peso proporcional à taxa de conversão de cada grupo
--     → Grupos que convertem mais recebem mais abordagens
--     → O peso cresce gradualmente com os dados, sem saltos bruscos
--
-- DENTRO DO GRUPO SELECIONADO:
--   ORDER BY (lead_score * POWER(random(), 0.5)) DESC LIMIT 1
--   → Favorece clínicas com maior score, mas com variação para não repetir sempre a mesma
--
-- EVOLUÇÃO DO EPSILON:
--   0 conversões  → epsilon = 1.00 → 100% exploração uniforme
--   10 conversões → epsilon = 0.80 → 80% explore, 20% exploit
--   25 conversões → epsilon = 0.50 → 50/50
--   40 conversões → epsilon = 0.20 → 20% explore, 80% exploit
--   50+ convers.  → epsilon = 0.20 → estabiliza (nunca para de explorar)
--
-- PREMISSAS:
--   - sdr_contacts.place_id (TEXT) e sdr_contacts.stage (TEXT: 'success'/'failed'/'in_progress')
--   - google_maps_signals.phone_e164 preenchido para clínicas elegíveis
--   - google_ads_signals join via place_id (usa todos os scraps disponíveis)
--
-- USO (n8n):
--   POST /rest/v1/rpc/pick_next_clinic
--   Body: {}
-- ============================================================================

CREATE OR REPLACE FUNCTION pick_next_clinic()
RETURNS TABLE (
    place_id         TEXT,
    clinic_name      TEXT,
    clinic_phone     TEXT,
    lead_score       NUMERIC,
    ads_group        TEXT,     -- 'ads_high' | 'ads_mid' | 'ads_low'
    google_ads_count INT,
    google_reviews   INT,
    google_rating    NUMERIC,
    selection_mode   TEXT      -- 'explore' | 'exploit'
)
LANGUAGE plpgsql
AS $$
DECLARE
    -- Contadores globais
    v_total_conversions INT;
    v_total_attempts    INT;

    -- Contadores por grupo
    v_att_high  INT; v_conv_high INT;
    v_att_mid   INT; v_conv_mid  INT;
    v_att_low   INT; v_conv_low  INT;

    -- Algoritmo
    v_epsilon        NUMERIC;
    v_exploit        BOOLEAN;
    v_selected_group TEXT;

    -- Taxas de conversão para exploit
    v_rate_high  NUMERIC;
    v_rate_mid   NUMERIC;
    v_rate_low   NUMERIC;
    v_rate_total NUMERIC;

    v_rand NUMERIC;
BEGIN

    -- ================================================================
    -- 1. Calcular tentativas e conversões por grupo
    --    (join clínicas scrapeadas com contatos já abordados)
    -- ================================================================
    SELECT
        COALESCE(SUM(st.conversions), 0),
        COALESCE(SUM(st.attempts), 0),
        COALESCE(SUM(st.attempts)     FILTER (WHERE st.ads_group = 'ads_high'), 0),
        COALESCE(SUM(st.conversions)  FILTER (WHERE st.ads_group = 'ads_high'), 0),
        COALESCE(SUM(st.attempts)     FILTER (WHERE st.ads_group = 'ads_mid'),  0),
        COALESCE(SUM(st.conversions)  FILTER (WHERE st.ads_group = 'ads_mid'),  0),
        COALESCE(SUM(st.attempts)     FILTER (WHERE st.ads_group = 'ads_low'),  0),
        COALESCE(SUM(st.conversions)  FILTER (WHERE st.ads_group = 'ads_low'),  0)
    INTO
        v_total_conversions, v_total_attempts,
        v_att_high, v_conv_high,
        v_att_mid,  v_conv_mid,
        v_att_low,  v_conv_low
    FROM (
        SELECT
            CASE
                WHEN gas.ads_count >= 5 THEN 'ads_high'
                WHEN gas.ads_count >= 2 THEN 'ads_mid'
                ELSE 'ads_low'
            END AS ads_group,
            COUNT(sc.place_id)                                          AS attempts,
            COUNT(sc.place_id) FILTER (WHERE sc.stage = 'success')     AS conversions
        FROM google_maps_signals gms
        JOIN google_ads_signals gas ON gms.place_id = gas.place_id
        LEFT JOIN sdr_contacts sc   ON sc.place_id  = gms.place_id
        WHERE gas.ads_count > 0
        GROUP BY ads_group
    ) st;

    -- ================================================================
    -- 2. Calcular epsilon — decresce com conversões, mínimo 0.20
    -- ================================================================
    v_epsilon := GREATEST(0.20, 1.0 - (v_total_conversions::NUMERIC / 50.0));

    -- ================================================================
    -- 3. Decidir explore vs exploit
    -- ================================================================
    v_exploit := (random() > v_epsilon);

    -- ================================================================
    -- 4. Selecionar grupo
    -- ================================================================
    IF NOT v_exploit THEN
        -- EXPLORE: uniforme entre os 3 grupos
        v_rand := random();
        IF    v_rand < 0.333 THEN v_selected_group := 'ads_high';
        ELSIF v_rand < 0.667 THEN v_selected_group := 'ads_mid';
        ELSE                       v_selected_group := 'ads_low';
        END IF;

    ELSE
        -- EXPLOIT: roleta proporcional à taxa de conversão
        v_rate_high  := v_conv_high::NUMERIC / GREATEST(v_att_high, 1);
        v_rate_mid   := v_conv_mid::NUMERIC  / GREATEST(v_att_mid,  1);
        v_rate_low   := v_conv_low::NUMERIC  / GREATEST(v_att_low,  1);
        v_rate_total := v_rate_high + v_rate_mid + v_rate_low;

        IF v_rate_total = 0 THEN
            -- Nenhum grupo converteu ainda → uniforme
            v_rand := random();
            IF    v_rand < 0.333 THEN v_selected_group := 'ads_high';
            ELSIF v_rand < 0.667 THEN v_selected_group := 'ads_mid';
            ELSE                       v_selected_group := 'ads_low';
            END IF;
        ELSE
            -- Roleta ponderada pela taxa de conversão
            v_rand := random() * v_rate_total;
            IF    v_rand < v_rate_high                    THEN v_selected_group := 'ads_high';
            ELSIF v_rand < (v_rate_high + v_rate_mid)     THEN v_selected_group := 'ads_mid';
            ELSE                                               v_selected_group := 'ads_low';
            END IF;
        END IF;
    END IF;

    -- ================================================================
    -- 5. Selecionar clínica candidata do grupo escolhido
    --    Exclui clínicas já abordadas (qualquer stage em sdr_contacts)
    --    Ordena por lead_score com ruído para variar seleção
    -- ================================================================
    RETURN QUERY
    WITH candidates AS (
        SELECT
            gms.place_id,
            gms.name            AS clinic_name,
            gms.phone_e164      AS clinic_phone,
            ROUND(
                  LEAST(gas.ads_count, 10) * 4.0
                + LEAST(COALESCE(gms.reviews_count, 0), 300) * 0.1
                + COALESCE(gms.rating, 0) * 4.0
                + CASE WHEN gms.website IS NOT NULL AND gms.website != ''
                       THEN 10.0 ELSE 0.0 END
            , 2)                AS lead_score,
            CASE
                WHEN gas.ads_count >= 5 THEN 'ads_high'
                WHEN gas.ads_count >= 2 THEN 'ads_mid'
                ELSE                        'ads_low'
            END                 AS ads_group,
            gas.ads_count       AS google_ads_count,
            gms.reviews_count   AS google_reviews,
            gms.rating          AS google_rating
        FROM google_maps_signals gms
        JOIN google_ads_signals gas
            ON gms.place_id = gas.place_id
        WHERE gas.ads_count > 0
          AND gms.phone_e164 IS NOT NULL
          AND gms.phone_e164 != ''
          -- Excluir clínicas já abordadas (independente do resultado)
          AND gms.place_id NOT IN (
              SELECT place_id FROM sdr_contacts
          )
    )
    SELECT
        c.place_id,
        c.clinic_name,
        c.clinic_phone,
        c.lead_score,
        c.ads_group,
        c.google_ads_count,
        c.google_reviews,
        c.google_rating,
        CASE WHEN v_exploit THEN 'exploit' ELSE 'explore' END AS selection_mode
    FROM candidates c
    WHERE c.ads_group = v_selected_group
    ORDER BY (c.lead_score * POWER(random(), 0.5)) DESC
    LIMIT 1;

END;
$$;

-- ============================================================================
-- GRANT para o role que o n8n usa (anon ou service_role)
-- ============================================================================
GRANT EXECUTE ON FUNCTION pick_next_clinic() TO anon;
GRANT EXECUTE ON FUNCTION pick_next_clinic() TO service_role;
