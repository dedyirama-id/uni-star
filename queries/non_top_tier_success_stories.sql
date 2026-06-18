-- 05_non_top_tier_success_stories.sql
-- Mencari 10 startup dengan valuasi tertinggi yang didirikan oleh founder Non-Top Tier
SELECT 
    c.company_name,
    c.industry,
    e.executive_name,
    e.university_name,
    e.tier_flag,
    f.valuation_usd,
    f.company_age_years
FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
JOIN read_parquet('s3://gold/dim_executive.parquet') e ON f.executive_name = e.executive_name
WHERE e.tier_flag NOT LIKE 'Top Tier%'
ORDER BY f.valuation_usd DESC
LIMIT 10;
