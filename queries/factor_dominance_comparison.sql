WITH company_level AS (
    SELECT
        f.company_key,
        MAX(f.valuation_usd) AS valuation_usd,
        MIN(CASE
            WHEN e.qs_world_ranking IS NOT NULL THEN e.qs_world_ranking
        END) AS best_qs_rank,
        SUM(CASE
            WHEN e.tier_flag = 'Unranked Higher Ed' THEN 1
            ELSE 0
        END) AS unranked_university_count,
        c.industry,
        c.country,
        MAX(f.company_age_years) AS company_age_years
    FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
    JOIN read_parquet('s3://gold/dim_company.parquet') c
        ON f.company_key = c.company_key
    JOIN read_parquet('s3://gold/dim_executive.parquet') e
        ON f.executive_key = e.executive_key
    WHERE f.valuation_usd > 0
      AND f.company_age_years IS NOT NULL
      AND c.industry IS NOT NULL
      AND c.country IS NOT NULL
    GROUP BY f.company_key, c.industry, c.country
),
model_data AS (
    SELECT
        company_key,
        LN(valuation_usd) AS log_valuation_usd,
        CASE
            WHEN best_qs_rank <= 100 THEN 'Top Tier Elite (Top 100)'
            WHEN best_qs_rank <= 500 THEN 'Mid Tier (101-500)'
            WHEN best_qs_rank > 500 THEN 'Non-Top Tier (>500)'
            WHEN unranked_university_count > 0 THEN 'Unranked Higher Ed'
            ELSE 'Unknown Education'
        END AS university_tier,
        industry,
        country,
        CASE
            WHEN company_age_years <= 5 THEN '0-5 Years'
            WHEN company_age_years <= 10 THEN '6-10 Years'
            WHEN company_age_years <= 20 THEN '11-20 Years'
            ELSE '20+ Years'
        END AS company_age_bucket
    FROM company_level
),
overall AS (
    SELECT AVG(log_valuation_usd) AS overall_mean
    FROM model_data
),
total_variance AS (
    SELECT
        SUM(POWER(m.log_valuation_usd - o.overall_mean, 2)) AS total_sum_squares
    FROM model_data m
    CROSS JOIN overall o
),
factor_groups AS (
    SELECT 'university_tier' AS factor_name, university_tier AS factor_value, COUNT(*) AS n, AVG(log_valuation_usd) AS group_mean
    FROM model_data
    GROUP BY university_tier

    UNION ALL

    SELECT 'industry' AS factor_name, industry AS factor_value, COUNT(*) AS n, AVG(log_valuation_usd) AS group_mean
    FROM model_data
    GROUP BY industry

    UNION ALL

    SELECT 'country' AS factor_name, country AS factor_value, COUNT(*) AS n, AVG(log_valuation_usd) AS group_mean
    FROM model_data
    GROUP BY country

    UNION ALL

    SELECT 'company_age_bucket' AS factor_name, company_age_bucket AS factor_value, COUNT(*) AS n, AVG(log_valuation_usd) AS group_mean
    FROM model_data
    GROUP BY company_age_bucket
)
SELECT
    g.factor_name,
    COUNT(*) AS group_count,
    SUM(g.n) AS observation_count,
    ROUND(SUM(g.n * POWER(g.group_mean - o.overall_mean, 2)), 4) AS between_group_sum_squares,
    ROUND(MAX(tv.total_sum_squares), 4) AS total_sum_squares,
    ROUND(SUM(g.n * POWER(g.group_mean - o.overall_mean, 2)) / NULLIF(MAX(tv.total_sum_squares), 0), 4) AS variance_explained_ratio
FROM factor_groups g
CROSS JOIN overall o
CROSS JOIN total_variance tv
WHERE g.factor_value IS NOT NULL
GROUP BY g.factor_name
ORDER BY variance_explained_ratio DESC;
