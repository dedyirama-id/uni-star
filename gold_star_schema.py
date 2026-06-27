import duckdb
import os
from dotenv import load_dotenv
from deltalake import DeltaTable
import pandas as pd

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

def build_startup_founders(df_startups):
    """
    Expands the comma-separated Kaggle Founders column into one founder row per
    company. This keeps all startup companies available for Gold analysis even
    when Wikidata does not have university data for the founder.
    """
    founder_rows = []
    for _, row in df_startups.iterrows():
        company_name = row.get("Company")
        founders = row.get("Founders")

        if pd.isna(company_name):
            continue

        founder_names = []
        if not pd.isna(founders):
            founder_names = [
                name.strip()
                for name in str(founders).split(",")
                if name.strip()
            ]

        if not founder_names:
            founder_names = ["Unknown Founder"]

        for founder_name in founder_names:
            founder_rows.append({
                "company_name": company_name,
                "founder_name": founder_name,
                "founder_match_key": founder_name.lower().strip(),
            })

    return pd.DataFrame(founder_rows).drop_duplicates()

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
    con.register('startup_founders', build_startup_founders(df_startups))
    
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
            WITH founder_education AS (
                SELECT DISTINCT
                    sf.founder_name AS executive_name,
                    e.universityLabel AS highest_education_institution,
                    e.degreeLabel AS highest_degree,
                    e.QS_Rank_Num AS qs_world_ranking,
                    e.University_Tier_Flag AS tier_flag
                FROM startup_founders sf
                LEFT JOIN silver_executives e
                    ON sf.founder_match_key = LOWER(TRIM(e.executiveLabel))
            ),
            executive_candidates AS (
                SELECT DISTINCT
                    executive_name,
                    highest_education_institution,
                    COALESCE(highest_degree, 'Unknown') AS highest_degree,
                    qs_world_ranking,
                    COALESCE(tier_flag, 'Unknown Education') AS tier_flag
                FROM founder_education
                WHERE executive_name IS NOT NULL
            )
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY executive_name, COALESCE(highest_education_institution, 'Unknown')
                ) AS executive_key,
                LOWER(REPLACE(executive_name, ' ', '_'))
                    || '_'
                    || LOWER(REPLACE(COALESCE(highest_education_institution, 'unknown'), ' ', '_')) AS executive_id,
                executive_name,
                highest_education_institution,
                highest_degree,
                qs_world_ranking,
                tier_flag
            FROM executive_candidates
        ) TO 's3://gold/dim_executive.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
    """)

    # 2b. Coverage audit table
    print("       - Creating education_coverage_audit")
    con.execute("""
        COPY (
            WITH founder_education AS (
                SELECT
                    sf.company_name,
                    sf.founder_name,
                    e.universityLabel AS highest_education_institution
                FROM startup_founders sf
                LEFT JOIN silver_executives e
                    ON sf.founder_match_key = LOWER(TRIM(e.executiveLabel))
            ),
            company_coverage AS (
                SELECT
                    company_name,
                    MAX(CASE
                        WHEN highest_education_institution IS NOT NULL THEN 1
                        ELSE 0
                    END) AS has_wikidata_university
                FROM founder_education
                GROUP BY company_name
            )
            SELECT
                (SELECT COUNT(*) FROM company_coverage) AS total_companies,
                (SELECT COUNT(*) FROM company_coverage WHERE has_wikidata_university = 1) AS companies_with_wikidata_university,
                (SELECT COUNT(*) FROM company_coverage WHERE has_wikidata_university = 0) AS companies_without_wikidata_university,
                COUNT(DISTINCT company_name || '|' || founder_name) AS founder_company_rows,
                COUNT(DISTINCT CASE
                    WHEN highest_education_institution IS NOT NULL
                    THEN company_name || '|' || founder_name || '|' || highest_education_institution
                END) AS founder_university_rows,
                ROUND(
                    (SELECT COUNT(*) FROM company_coverage WHERE has_wikidata_university = 1)
                    * 100.0 / NULLIF((SELECT COUNT(*) FROM company_coverage), 0),
                    2
                ) AS university_coverage_pct
            FROM founder_education
        ) TO 's3://gold/education_coverage_audit.parquet' (FORMAT PARQUET, OVERWRITE_OR_IGNORE);
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
                        WHEN de.tier_flag LIKE 'Unranked%' THEN (s.Company_Age_Years * 2.0)
                        WHEN de.tier_flag LIKE 'Non-Top%' THEN (s.Company_Age_Years * 1.5)
                        WHEN de.tier_flag = 'Unknown Education' THEN (s.Company_Age_Years * 1.0)
                        ELSE (s.Company_Age_Years * 1.0)
                    END AS experience_grit_index
                FROM silver_startups s
                JOIN dim_company dc ON s.Company = dc.company_name
                JOIN startup_founders sf ON s.Company = sf.company_name
                JOIN dim_executive de ON sf.founder_name = de.executive_name
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
