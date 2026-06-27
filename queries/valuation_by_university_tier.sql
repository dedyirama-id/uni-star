-- Apakah tier universitas eksekutif berkaitan dengan valuasi perusahaan?
-- Query ini membandingkan jumlah perusahaan, total valuasi, rata-rata valuasi,
-- median valuasi, dan rata-rata log valuasi pada setiap tier universitas.

SELECT
    e.tier_flag,
    COUNT(*) AS executive_company_pairs,
    COUNT(DISTINCT f.company_key) AS total_companies,
    COUNT(DISTINCT e.executive_name) AS total_executives,
    ROUND(SUM(f.valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(f.valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(f.valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd,
    ROUND(AVG(LN(f.valuation_usd)), 4) AS avg_log_valuation
FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
JOIN read_parquet('s3://gold/dim_executive.parquet') e
    ON f.executive_key = e.executive_key
WHERE e.tier_flag IS NOT NULL
  AND e.tier_flag <> 'Unknown Education'
  AND f.valuation_usd > 0
GROUP BY e.tier_flag
ORDER BY avg_valuation_billion_usd DESC;
