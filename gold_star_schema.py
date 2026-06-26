import duckdb
import os
from dotenv import load_dotenv
from deltalake import DeltaTable

load_dotenv()

MINIO_ENDPOINT_HOST = os.getenv("MINIO_ENDPOINT_HOST", "localhost:9000")
MINIO_ENDPOINT_URL = os.getenv("MINIO_ENDPOINT_URL", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
import boto3

STORAGE_OPTIONS = {
    "AWS_ACCESS_KEY_ID": MINIO_ACCESS_KEY,
    "AWS_SECRET_ACCESS_KEY": MINIO_SECRET_KEY,
    "AWS_ENDPOINT_URL": MINIO_ENDPOINT_URL,
    "AWS_REGION": "us-east-1",
    "AWS_ALLOW_HTTP": "true",
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true"
}

GOLD_BUCKET = "gold"

def get_s3_client():
    """
    Initializes and returns a boto3 S3 client configured for the MinIO Data Lake.
    """
    return boto3.client(
        's3',
        endpoint_url=STORAGE_OPTIONS["AWS_ENDPOINT_URL"],
        aws_access_key_id=STORAGE_OPTIONS["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=STORAGE_OPTIONS["AWS_SECRET_ACCESS_KEY"],
        region_name=STORAGE_OPTIONS["AWS_REGION"]
    )

def create_gold_layer():
    """
    Executes the Gold layer aggregation and dimensional modeling pipeline.
    
    Leverages DuckDB as an in-process OLAP engine to transform Silver layer 
    Parquet datasets into a Star Schema (Fact and Dimension tables). 
    The resulting tables are written back to the Gold layer in MinIO.
    """
    print("[INFO] Connecting to DuckDB and configuring S3 access...")
    con = duckdb.connect()
    
    con.execute(f"INSTALL httpfs;")
    con.execute(f"LOAD httpfs;")
    con.execute(f"SET s3_endpoint='{MINIO_ENDPOINT_HOST}';")
    con.execute(f"SET s3_access_key_id='{MINIO_ACCESS_KEY}';")
    con.execute(f"SET s3_secret_access_key='{MINIO_SECRET_KEY}';")
    con.execute(f"SET s3_use_ssl=false;")
    con.execute(f"SET s3_region='us-east-1';")
    con.execute(f"SET s3_url_style='path';")
    
    print("[INFO] Reading Silver Delta Tables into Pandas...")
    df_startups = DeltaTable('s3://silver/unicorn_startups', storage_options=STORAGE_OPTIONS).to_pandas()
    df_executives = DeltaTable('s3://silver/executive_profiles', storage_options=STORAGE_OPTIONS).to_pandas()
    
    con.register('silver_startups', df_startups)
    con.register('silver_executives', df_executives)
    
    s3_client = get_s3_client()
    try:
        s3_client.create_bucket(Bucket=GOLD_BUCKET)
    except:
        pass

    print("[INFO] Building Star Schema (Gold Layer)...")
    
    # 1. Dim Company
    print("       - Creating dim_company")
    con.execute("""
        COPY (
            SELECT
                ROW_NUMBER() OVER (ORDER BY company_name) AS company_key,
                LOWER(REPLACE(company_name, ' ', '_')) AS company_id,
                company_name,
                industry,
                country,
                continent,
                city
            FROM (
                SELECT DISTINCT
                    Company AS company_name,
                    Industry AS industry,
                    Country AS country,
                    Continent AS continent,
                    City AS city
                FROM silver_startups
                WHERE Company IS NOT NULL
            )
        ) TO 's3://gold/dim_company.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)

    # 2. Dim Executive
    print("       - Creating dim_executive")
    con.execute("""
        COPY (
            SELECT
                ROW_NUMBER() OVER (ORDER BY executive_name, highest_education_institution) AS executive_key,
                LOWER(REPLACE(executive_name, ' ', '_')) AS executive_id,
                executive_name,
                highest_education_institution,
                highest_degree,
                qs_world_ranking,
                tier_flag
            FROM (
                SELECT DISTINCT
                    executiveLabel AS executive_name,
                    universityLabel AS highest_education_institution,
                    degreeLabel AS highest_degree,
                    QS_Rank_Num AS qs_world_ranking,
                    University_Tier_Flag AS tier_flag
                FROM silver_executives
                WHERE executiveLabel IS NOT NULL
            )
        ) TO 's3://gold/dim_executive.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)

    # 3. Fact Valuation & Grit
    print("       - Creating fact_valuation_grit")
    con.execute("""
        COPY (
            WITH dim_company AS (
                SELECT *
                FROM read_parquet('s3://gold/dim_company.parquet')
            ),
            dim_executive AS (
                SELECT *
                FROM read_parquet('s3://gold/dim_executive.parquet')
            ),
            matched AS (
                SELECT
                    dc.company_key,
                    de.executive_key,
                    CAST(REPLACE(REPLACE(s.Valuation_Formatted, '$', ''), 'B', '') AS DOUBLE) * 1000000000 AS valuation_usd,
                    s.Valuation_Tier AS valuation_tier,
                    s.Year_Founded AS year_founded,
                    s.Company_Age_Years AS company_age_years,
                    -- Experience & Grit Index Logic:
                    -- Older companies reaching high valuations with non-traditional
                    -- founder backgrounds receive a higher Grit Index.
                    CASE
                        WHEN e.University_Tier_Flag LIKE 'Unranked%' THEN (s.Company_Age_Years * 2.0)
                        WHEN e.University_Tier_Flag LIKE 'Non-Top%' THEN (s.Company_Age_Years * 1.5)
                        ELSE (s.Company_Age_Years * 1.0)
                    END AS experience_grit_index
                FROM silver_startups s
                JOIN silver_executives e ON LOWER(s.Company) = LOWER(e.companyLabel)
                    OR LOWER(s.Founders) LIKE '%' || LOWER(e.executiveLabel) || '%'
                JOIN dim_company dc ON s.Company = dc.company_name
                JOIN dim_executive de ON e.executiveLabel = de.executive_name
                    AND e.universityLabel = de.highest_education_institution
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY company_key, executive_key) AS fact_valuation_grit_key,
                company_key,
                executive_key,
                valuation_usd,
                valuation_tier,
                year_founded,
                company_age_years,
                experience_grit_index
            FROM matched
        ) TO 's3://gold/fact_valuation_grit.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)
    
    print("[ OK ] Gold Layer Star Schema created successfully in S3!")

if __name__ == "__main__":
    create_gold_layer()
