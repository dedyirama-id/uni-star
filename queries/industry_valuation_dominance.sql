-- Apakah industri lebih dominan dalam menjelaskan valuasi?
-- Query ini mencari industri dengan rata-rata dan total valuasi terbesar.
-- Hasilnya dipakai sebagai pembanding terhadap pengaruh tier universitas.

WITH company_level AS (
    SELECT
        f.company_key,
        c.industry,
        MAX(f.valuation_usd) AS valuation_usd,
        AVG(f.experience_grit_index) AS experience_grit_index
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
    JOIN read_parquet('s3://gold/dim_company.parquet') c
        ON f.company_key = c.company_key
    WHERE c.industry IS NOT NULL
      AND f.valuation_usd > 0
    GROUP BY f.company_key, c.industry
)

SELECT
    industry,
    COUNT(*) AS total_companies,
    ROUND(SUM(valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd,
    ROUND(AVG(experience_grit_index), 2) AS avg_grit_index
FROM company_level
GROUP BY industry
HAVING COUNT(*) >= 2
ORDER BY avg_valuation_billion_usd DESC
LIMIT 10;
