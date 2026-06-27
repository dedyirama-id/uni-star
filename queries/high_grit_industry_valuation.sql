-- Analisis industri pada perusahaan dengan grit index tinggi.
-- Query ini melihat industri mana yang memiliki rata-rata valuasi tinggi
-- pada perusahaan yang memiliki experience grit index besar.

WITH high_grit_companies AS (
    SELECT
        f.company_key,
        MAX(f.valuation_usd) AS valuation_usd,
        MAX(f.company_age_years) AS company_age_years,
        AVG(f.experience_grit_index) AS experience_grit_index,
        c.industry,
        c.country,
        COUNT(DISTINCT f.executive_key) AS total_executives
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
    JOIN read_parquet('s3://gold/dim_company.parquet') c
        ON f.company_key = c.company_key
    WHERE f.valuation_usd > 0
      AND f.experience_grit_index IS NOT NULL
      AND c.industry IS NOT NULL
    GROUP BY f.company_key, c.industry, c.country
    HAVING AVG(f.experience_grit_index) >= 25
)

SELECT
    industry,
    COUNT(*) AS total_companies,
    SUM(total_executives) AS total_executives,
    ROUND(AVG(company_age_years), 2) AS avg_company_age_years,
    ROUND(AVG(experience_grit_index), 2) AS avg_grit_index,
    ROUND(SUM(valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd
FROM high_grit_companies
GROUP BY industry
HAVING COUNT(*) >= 1
ORDER BY avg_valuation_billion_usd DESC;
