import duckdb
import boto3

STORAGE_OPTIONS = {
    "AWS_ACCESS_KEY_ID": "admin",
    "AWS_SECRET_ACCESS_KEY": "password",
    "AWS_ENDPOINT_URL": "http://localhost:9000",
    "AWS_REGION": "us-east-1"
}

GOLD_BUCKET = "gold"

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=STORAGE_OPTIONS["AWS_ENDPOINT_URL"],
        aws_access_key_id=STORAGE_OPTIONS["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=STORAGE_OPTIONS["AWS_SECRET_ACCESS_KEY"],
        region_name=STORAGE_OPTIONS["AWS_REGION"]
    )

def create_gold_layer():
    print("Connecting to DuckDB and configuring S3 access...")
    con = duckdb.connect()
    
    con.execute(f"INSTALL httpfs;")
    con.execute(f"LOAD httpfs;")
    con.execute(f"SET s3_endpoint='localhost:9000';")
    con.execute(f"SET s3_access_key_id='minioadmin';")
    con.execute(f"SET s3_secret_access_key='minioadmin';")
    con.execute(f"SET s3_use_ssl=false;")
    con.execute(f"SET s3_region='us-east-1';")
    con.execute(f"SET s3_url_style='path';")
    
    print("Reading Silver Parquet Tables...")
    con.execute("CREATE OR REPLACE VIEW silver_startups AS SELECT * FROM read_parquet('s3://silver/unicorn_startups/*.parquet');")
    con.execute("CREATE OR REPLACE VIEW silver_executives AS SELECT * FROM read_parquet('s3://silver/executive_profiles/*.parquet');")
    
    s3_client = get_s3_client()
    try:
        s3_client.create_bucket(Bucket=GOLD_BUCKET)
    except:
        pass

    print("Building Star Schema (Gold Layer)...")
    
    # 1. Dim Company
    print("-> Creating dim_company")
    con.execute("""
        COPY (
            SELECT DISTINCT
                Company AS company_name,
                Industry AS industry,
                Country AS country,
                Continent AS continent,
                City AS city
            FROM silver_startups
        ) TO 's3://gold/dim_company.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)

    # 2. Dim Executive
    print("-> Creating dim_executive")
    con.execute("""
        COPY (
            SELECT DISTINCT
                executiveLabel AS executive_name,
                universityLabel AS university_name,
                degreeLabel AS degree,
                QS_Rank AS qs_rank,
                University_Tier_Flag AS tier_flag
            FROM silver_executives
        ) TO 's3://gold/dim_executive.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)

    # 3. Fact Valuation & Grit
    print("-> Creating fact_valuation_grit")
    con.execute("""
        COPY (
            SELECT 
                s.Company AS company_name,
                e.executiveLabel AS executive_name,
                CAST(REPLACE(REPLACE(s.Valuation_Formatted, '$', ''), 'B', '') AS DOUBLE) * 1000000000 AS valuation_usd,
                s.Valuation_Tier AS valuation_tier,
                s.Year_Founded AS year_founded,
                s.Company_Age_Years AS company_age_years,
                -- Example Experience & Grit Index logic:
                -- Older company reaching high valuation + Non-Top Tier founder = Higher Grit Index
                CASE 
                    WHEN e.University_Tier_Flag LIKE 'Non-Top%' THEN (s.Company_Age_Years * 1.5)
                    WHEN e.University_Tier_Flag LIKE 'Non-Formal%' THEN (s.Company_Age_Years * 2.0)
                    ELSE (s.Company_Age_Years * 1.0)
                END AS experience_grit_index
            FROM silver_startups s
            JOIN silver_executives e ON LOWER(s.Company) = LOWER(e.companyLabel) 
                OR LOWER(s.Founders) LIKE '%' || LOWER(e.executiveLabel) || '%'
        ) TO 's3://gold/fact_valuation_grit.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)
    
    print("Gold Layer Star Schema created successfully in S3!")

if __name__ == "__main__":
    create_gold_layer()
