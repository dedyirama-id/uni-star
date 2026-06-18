-- 02_top_industries_by_grit.sql
-- Melihat industri apa yang memiliki tingkat ketahanan (Grit Index) tertinggi
SELECT 
    c.industry,
    COUNT(DISTINCT c.company_name) AS total_companies,
    AVG(f.experience_grit_index) AS avg_grit_index,
    MAX(f.experience_grit_index) AS max_grit_index
FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
GROUP BY c.industry
HAVING COUNT(DISTINCT c.company_name) > 1
ORDER BY avg_grit_index DESC
LIMIT 10;
