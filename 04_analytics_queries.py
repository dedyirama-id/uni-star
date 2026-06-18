import duckdb
import sys
import io

# Fix for printing DuckDB execution plan tree characters in Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def run_analytics():
    print("Connecting to DuckDB S3 Gold Layer...")
    con = duckdb.connect()
    con.execute(f"INSTALL httpfs;")
    con.execute(f"LOAD httpfs;")
    con.execute(f"SET s3_endpoint='localhost:9000';")
    con.execute(f"SET s3_access_key_id='minioadmin';")
    con.execute(f"SET s3_secret_access_key='minioadmin';")
    con.execute(f"SET s3_use_ssl=false;")
    con.execute(f"SET s3_region='us-east-1';")
    con.execute(f"SET s3_url_style='path';")

    print("\n--- QUERY 1: Rata-rata Umur Perusahaan (Grit) berdasarkan Latar Belakang Founder ---")
    query1 = """
        SELECT 
            e.tier_flag,
            COUNT(DISTINCT c.company_name) as total_companies,
            AVG(f.company_age_years) as avg_company_age
        FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
        JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
        JOIN read_parquet('s3://gold/dim_executive.parquet') e ON f.executive_name = e.executive_name
        WHERE e.tier_flag IS NOT NULL
        GROUP BY e.tier_flag
        ORDER BY avg_company_age DESC;
    """
    print(con.execute(query1).df())

    print("\n--- QUERY 2: Total Valuasi (USD) Industri AI oleh Founder Non-Top Tier ---")
    query2 = """
        SELECT 
            c.industry,
            SUM(f.valuation_usd) as total_valuation
        FROM read_parquet('s3://gold/fact_valuation_grit.parquet') f
        JOIN read_parquet('s3://gold/dim_company.parquet') c ON f.company_name = c.company_name
        JOIN read_parquet('s3://gold/dim_executive.parquet') e ON f.executive_name = e.executive_name
        WHERE c.industry LIKE '%Artificial Intelligence%' 
          AND e.tier_flag NOT LIKE 'Top Tier%'
        GROUP BY c.industry;
    """
    print(con.execute(query2).df())
    
    print("\n--- BONUS: Query Explanation Analysis (Filter Pushdown) ---")
    explain_query = "EXPLAIN ANALYZE " + query2
    explain_result = con.execute(explain_query).fetchall()
    
    with open("explain_analyze_output.txt", "w", encoding="utf-8") as f:
        for row in explain_result:
            plan_str = str(row[1])
            print(plan_str)
            f.write(plan_str + "\n")
    print("\n[SUCCESS] Execution plan saved to explain_analyze_output.txt")

if __name__ == "__main__":
    run_analytics()
