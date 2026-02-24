-- ============================================================================
-- google_ICPs — Query de análise de leads do Google (ICPs)
-- ============================================================================
--
-- LEAD SCORE (0–100 pts) — mesma fórmula do pick_next_clinic()
--
-- Dados reais (percentis de clínicas elegíveis):
--   ads_count : p50=7,  p75=23,  p90=300, max=900
--   reviews   : p50=47, p75=82,  p90=188, max=36284
--   rating    : avg=4.78, p50=5.0 (quase sem variação isolado)
--
-- score_ads = LN(ads+1) / LN(901) * 35
-- score_rep = rating * LN(reviews+1) / (5 * LN(189)) * 55
-- score_web = 10 se tem website
-- ============================================================================

WITH google_leads AS (
    SELECT
        gms.place_id,
        gms.name,
        gms.website,
        gms.rating                                          AS google_rating,
        gms.reviews_count                                   AS google_reviews,
        gms.phone_e164                                      AS google_phone,
        gas.domain,
        gas.ads_count                                       AS google_ads_count,

        -- Lead Score (0–100+) — escala logarítmica baseada em percentis reais
        ROUND(
            -- Ads: 35pts — escala log normalizada pelo max real (900)
            LN(gas.ads_count::NUMERIC + 1) / LN(901.0) * 35.0

            -- Reputação credível: 55pts — rating × volume de reviews
            -- Normalizado por 5★ com 188 reviews (p90)
            -- Garante: 4.8★×3000 reviews >> 5★×12 reviews
            + COALESCE(gms.rating, 0)
              * LN(COALESCE(gms.reviews_count, 0)::NUMERIC + 1)
              / (5.0 * LN(189.0)) * 55.0

            -- Website: 10pts — presença digital mínima confirmada
            + CASE WHEN gms.website IS NOT NULL AND gms.website != '' THEN 10.0 ELSE 0.0 END
        , 2)                                                AS lead_score,

        -- Debug: componentes separados
        ROUND(LN(gas.ads_count::NUMERIC + 1) / LN(901.0) * 35.0, 2)   AS score_ads,
        ROUND(
            COALESCE(gms.rating, 0)
            * LN(COALESCE(gms.reviews_count, 0)::NUMERIC + 1)
            / (5.0 * LN(189.0)) * 55.0
        , 2)                                                AS score_rep,
        CASE WHEN gms.website IS NOT NULL AND gms.website != '' THEN 10 ELSE 0 END AS score_web

    FROM google_maps_signals gms
    INNER JOIN google_ads_signals gas
        ON gms.place_id = gas.place_id
        AND gms.search_run_id::text = gas.search_run_id

    WHERE gas.ads_count > 0
    --AND gms.search_run_id = '57ff728d-b280-4814-9685-c32df05216b8'
)

SELECT
    *,
    CASE
        WHEN lead_score >= 80 THEN 'HOT 🔥'
        WHEN lead_score >= 60 THEN 'WARM 🌡️'
        WHEN lead_score >= 40 THEN 'COLD ❄️'
        ELSE 'ICE 🧊'
    END AS lead_temperature

FROM google_leads
ORDER BY lead_score DESC, google_ads_count DESC, google_reviews DESC;
