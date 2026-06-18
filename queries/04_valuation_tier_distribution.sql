-- 04_valuation_tier_distribution.sql
-- Distribusi jumlah perusahaan (Unicorn, Decacorn, Hectocorn) berdasarkan benua
SELECT 
    c.continent,
    f.valuation_tier,
    COUNT(DISTINCT c.company_name) AS total_companies,
    SUM(f.valuation_usd) AS total_valuation_usd
FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
WHERE c.continent IS NOT NULL
GROUP BY c.continent, f.valuation_tier
ORDER BY c.continent, total_companies DESC;
