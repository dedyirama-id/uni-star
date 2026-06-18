-- 03_top_universities_producing_founders.sql
-- Top 10 Universitas yang paling banyak mencetak eksekutif / founder Unicorn
SELECT 
    e.university_name,
    e.tier_flag,
    COUNT(DISTINCT e.executive_name) AS total_founders,
    COUNT(DISTINCT f.company_name) AS total_unicorns_founded,
    SUM(f.valuation_usd) AS total_valuation_contribution
FROM read_parquet('s3://gold/dim_executive.parquet') e
JOIN read_parquet('s3://gold/fact_valuation_grit.parquet') f ON e.executive_name = f.executive_name
WHERE e.university_name != 'Unknown' AND e.university_name IS NOT NULL
GROUP BY e.university_name, e.tier_flag
ORDER BY total_founders DESC
LIMIT 10;
