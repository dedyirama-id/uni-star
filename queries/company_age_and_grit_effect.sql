WITH company_level AS (
    SELECT
        company_key,
        MAX(valuation_usd) AS valuation_usd,
        MAX(company_age_years) AS company_age_years,
        AVG(experience_grit_index) AS experience_grit_index
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet')
    WHERE company_age_years IS NOT NULL
      AND experience_grit_index IS NOT NULL
      AND valuation_usd > 0
    GROUP BY company_key
)

SELECT
    CASE
        WHEN company_age_years <= 5 THEN '0-5 Years'
        WHEN company_age_years <= 10 THEN '6-10 Years'
        WHEN company_age_years <= 20 THEN '11-20 Years'
        ELSE '20+ Years'
    END AS company_age_bucket,
    COUNT(*) AS total_companies,
    ROUND(AVG(company_age_years), 2) AS avg_company_age_years,
    ROUND(AVG(experience_grit_index), 2) AS avg_grit_index,
    ROUND(SUM(valuation_usd) / 1000000000, 2) AS total_valuation_billion_usd,
    ROUND(AVG(valuation_usd) / 1000000000, 2) AS avg_valuation_billion_usd,
    ROUND(MEDIAN(valuation_usd) / 1000000000, 2) AS median_valuation_billion_usd
FROM company_level
GROUP BY company_age_bucket
ORDER BY avg_valuation_billion_usd DESC;
