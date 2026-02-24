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
--   epsilon = max(0.2, 1 - total_scheduled/50)
--
--   EXPLORE (epsilon % do tempo):
--     Sorteia grupo uniformemente — garante cobertura de todos os segmentos
--
--   EXPLOIT (1-epsilon % do tempo):
--     Sorteia grupo com peso proporcional à taxa de conversão de cada grupo
--     → Grupos que convertem mais (status='scheduled') recebem mais abordagens
--     → O peso cresce gradualmente com os dados, sem saltos bruscos
--
-- DENTRO DO GRUPO SELECIONADO:
--   ORDER BY (lead_score * POWER(random(), 0.5)) DESC LIMIT 1
--   → Favorece clínicas com maior score, mas com variação para não repetir a mesma
--
-- EVOLUÇÃO DO EPSILON:
--   0  reuniões → epsilon = 1.00 → 100% exploração uniforme
--   10 reuniões → epsilon = 0.80 → 80% explore, 20% exploit
--   25 reuniões → epsilon = 0.50 → 50/50
--   40 reuniões → epsilon = 0.20 → 20% explore, 80% exploit
--   50+ reuniões → epsilon = 0.20 → estabiliza (nunca para de explorar)
--
-- DEPENDÊNCIAS (executar sdr_schema.sql primeiro):
--   - sdr_contacts: rastreia clínicas abordadas e conversões (status='scheduled')
--   - google_maps_signals: dados da clínica (phone_e164, rating, reviews, website)
--   - google_ads_signals: dados de anúncios (ads_count, place_id)
--
-- USO (n8n):
--   POST /rest/v1/rpc/pick_next_clinic
--   Body: {}
-- ============================================================================

CREATE OR REPLACE FUNCTION pick_next_clinic()
RETURNS TABLE (
    out_place_id         TEXT,
    out_clinic_name      TEXT,
    out_clinic_phone     TEXT,
    out_lead_score       NUMERIC,
    out_ads_group        TEXT,
    out_google_ads_count INT,
    out_google_reviews   INT,
    out_google_rating    NUMERIC,
    out_selection_mode   TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    -- Totais e contadores por grupo
    v_total_scheduled INT;
    v_att_high INT; v_conv_high INT;
    v_att_mid  INT; v_conv_mid  INT;
    v_att_low  INT; v_conv_low  INT;

    -- Algoritmo
    v_epsilon        NUMERIC;
    v_exploit        BOOLEAN;
    v_selected_group TEXT;

    -- Taxas para exploit
    v_rate_high  NUMERIC;
    v_rate_mid   NUMERIC;
    v_rate_low   NUMERIC;
    v_rate_total NUMERIC;

    v_rand NUMERIC;
BEGIN

    -- ================================================================
    -- 1. Calcular tentativas e conversões por grupo
    --    Tentativas = clínicas em sdr_contacts (qualquer status)
    --    Conversões = sdr_contacts.status = 'scheduled'
    --    Join via place_id (disponível em sdr_contacts)
    -- ================================================================
    SELECT
        COALESCE(SUM(st.conv), 0),
        COALESCE(SUM(st.att)  FILTER (WHERE st.grp = 'ads_high'), 0),
        COALESCE(SUM(st.conv) FILTER (WHERE st.grp = 'ads_high'), 0),
        COALESCE(SUM(st.att)  FILTER (WHERE st.grp = 'ads_mid'),  0),
        COALESCE(SUM(st.conv) FILTER (WHERE st.grp = 'ads_mid'),  0),
        COALESCE(SUM(st.att)  FILTER (WHERE st.grp = 'ads_low'),  0),
        COALESCE(SUM(st.conv) FILTER (WHERE st.grp = 'ads_low'),  0)
    INTO
        v_total_scheduled,
        v_att_high, v_conv_high,
        v_att_mid,  v_conv_mid,
        v_att_low,  v_conv_low
    FROM (
        SELECT
            CASE
                WHEN gas.ads_count >= 5 THEN 'ads_high'
                WHEN gas.ads_count >= 2 THEN 'ads_mid'
                ELSE 'ads_low'
            END AS grp,
            COUNT(sc.id)                                            AS att,
            COUNT(sc.id) FILTER (WHERE sc.status = 'scheduled')    AS conv
        FROM google_maps_signals gms
        JOIN google_ads_signals  gas ON gas.place_id = gms.place_id
        LEFT JOIN sdr_contacts   sc  ON sc.place_id  = gms.place_id
        WHERE gas.ads_count > 0
        GROUP BY grp
    ) st;

    -- ================================================================
    -- 2. Epsilon decrescente — mínimo 20% de exploração sempre
    -- ================================================================
    v_epsilon := GREATEST(0.20, 1.0 - (v_total_scheduled::NUMERIC / 50.0));
    v_exploit := (random() > v_epsilon);

    -- ================================================================
    -- 3. Selecionar grupo
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
            -- Roleta ponderada
            v_rand := random() * v_rate_total;
            IF    v_rand < v_rate_high                THEN v_selected_group := 'ads_high';
            ELSIF v_rand < (v_rate_high + v_rate_mid) THEN v_selected_group := 'ads_mid';
            ELSE                                           v_selected_group := 'ads_low';
            END IF;
        END IF;
    END IF;

    -- ================================================================
    -- 4. Selecionar clínica candidata do grupo escolhido
    --    Exclui clínicas com place_id já em sdr_contacts (qualquer status)
    --    Ordena por lead_score com ruído para variar seleção
    -- ================================================================
    RETURN QUERY
    WITH candidates AS (
        SELECT
            gms.place_id                AS c_place_id,
            gms.name                    AS c_clinic_name,
            gms.phone_e164              AS c_clinic_phone,
            ROUND(
                  LEAST(gas.ads_count, 10) * 4.0
                + LEAST(COALESCE(gms.reviews_count, 0), 300) * 0.1
                + COALESCE(gms.rating, 0) * 4.0
                + CASE WHEN gms.website IS NOT NULL AND gms.website != ''
                       THEN 10.0 ELSE 0.0 END
            , 2)                        AS c_lead_score,
            CASE
                WHEN gas.ads_count >= 5 THEN 'ads_high'
                WHEN gas.ads_count >= 2 THEN 'ads_mid'
                ELSE 'ads_low'
            END                         AS c_ads_group,
            gas.ads_count               AS c_google_ads_count,
            gms.reviews_count           AS c_google_reviews,
            gms.rating                  AS c_google_rating
        FROM google_maps_signals gms
        JOIN google_ads_signals gas ON gas.place_id = gms.place_id
        WHERE gas.ads_count > 0
          AND gms.phone_e164 IS NOT NULL
          AND gms.phone_e164 != ''
          AND gms.place_id NOT IN (
              SELECT sc.place_id FROM sdr_contacts sc
              WHERE sc.place_id IS NOT NULL
          )
    )
    SELECT
        c.c_place_id,
        c.c_clinic_name,
        c.c_clinic_phone,
        c.c_lead_score,
        c.c_ads_group,
        c.c_google_ads_count,
        c.c_google_reviews,
        c.c_google_rating,
        CASE WHEN v_exploit THEN 'exploit'::TEXT ELSE 'explore'::TEXT END
    FROM candidates c
    WHERE c.c_ads_group = v_selected_group
    ORDER BY (c.c_lead_score * POWER(random(), 0.5)) DESC
    LIMIT 1;

END;
$$;

-- ============================================================================
-- GRANTS
-- ============================================================================
GRANT EXECUTE ON FUNCTION pick_next_clinic() TO anon;
GRANT EXECUTE ON FUNCTION pick_next_clinic() TO service_role;
