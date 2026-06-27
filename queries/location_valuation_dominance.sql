-- Apakah lokasi perusahaan lebih dominan dalam menjelaskan valuasi?
-- Query ini membandingkan negara berdasarkan jumlah perusahaan, total valuasi,
-- rata-rata valuasi, median valuasi, dan komposisi industri.

WITH company_level AS (
    SELECT
        f.company_key,
        c.country,
        c.continent,
        c.industry,
        MAX(f.valuation_usd) AS valuation_usd
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
    JOIN read_parquet('s3://gold/dim_company.parquet') c
        ON f.company_key = c.company_key
    WHERE c.country IS NOT NULL
      AND c.continent IS NOT NULL
      AND f.valuation_usd > 0
    GROUP BY f.company_key, c.country, c.continent, c.industry
)

SELECT
    country,
    continent,
    COUNT(*) AS total_companies,
    COUNT(DISTINCT industry) AS industry_diversity,
    ROUND(SUM(valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd
FROM company_level
GROUP BY country, continent
HAVING COUNT(*) >= 1
ORDER BY avg_valuation_billion_usd DESC
LIMIT 10;
