-- Analisis hubungan antara reputasi universitas dan grit index terhadap valuasi.
-- Query ini membandingkan valuasi perusahaan berdasarkan tier universitas eksekutif
-- dan kategori grit index perusahaan.

WITH base_data AS (
    SELECT
        f.company_name,
        f.executive_name,
        f.valuation_usd,
        f.company_age_years,
        f.experience_grit_index,
        e.tier_flag,
        CASE
            WHEN f.experience_grit_index < 10 THEN 'Low Grit'
            WHEN f.experience_grit_index < 25 THEN 'Medium Grit'
            ELSE 'High Grit'
        END AS grit_level
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
    JOIN read_parquet('s3://gold/dim_executive.parquet') e
        ON f.executive_name = e.executive_name
    WHERE f.valuation_usd > 0
      AND f.experience_grit_index IS NOT NULL
      AND e.tier_flag IS NOT NULL
)

SELECT
    tier_flag AS university_tier,
    grit_level,
    COUNT(*) AS executive_company_pairs,
    COUNT(DISTINCT company_name) AS total_companies,
    ROUND(AVG(company_age_years), 2) AS avg_company_age_years,
    ROUND(AVG(experience_grit_index), 2) AS avg_grit_index,
    ROUND(SUM(valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd
FROM base_data
GROUP BY university_tier, grit_level
ORDER BY avg_valuation_billion_usd DESC;