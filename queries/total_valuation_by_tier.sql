-- 01_total_valuation_by_tier.sql
-- Menghitung total valuasi startup berdasarkan latar belakang Tier Universitas Founder
SELECT 
    e.tier_flag,
    COUNT(DISTINCT c.company_name) AS total_startups,
    SUM(f.valuation_usd) AS total_valuation_usd,
    AVG(f.valuation_usd) AS avg_valuation_usd
FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
JOIN read_parquet('s3://gold/dim_executive.parquet') e ON f.executive_name = e.executive_name
WHERE e.tier_flag IS NOT NULL
GROUP BY e.tier_flag
ORDER BY total_valuation_usd DESC;
