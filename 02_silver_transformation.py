import pandas as pd
import boto3



# S3 Storage Options for Pandas
PANDAS_STORAGE_OPTIONS = {
    "key": "minioadmin",
    "secret": "minioadmin",
    "client_kwargs": {"endpoint_url": "http://localhost:9000"}
}

BRONZE_BUCKET = "bronze"
SILVER_BUCKET = "silver"

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=PANDAS_STORAGE_OPTIONS["client_kwargs"]["endpoint_url"],
        aws_access_key_id=PANDAS_STORAGE_OPTIONS["key"],
        aws_secret_access_key=PANDAS_STORAGE_OPTIONS["secret"],
        region_name="us-east-1"
    )

def calculate_s3_folder_size(client, bucket, prefix):
    total_size = 0
    paginator = client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                total_size += obj['Size']
    return total_size

def process_silver():
    print("Reading data from Bronze Layer...")
    
    # Read Kaggle CSV
    df_kaggle = pd.read_csv(
        f"s3://{BRONZE_BUCKET}/kaggle_unicorn_startups.csv",
        storage_options=PANDAS_STORAGE_OPTIONS
    )
    
    # Read Wikidata CSV
    df_wiki = pd.read_csv(
        f"s3://{BRONZE_BUCKET}/wikidata_executive_profile.csv",
        storage_options=PANDAS_STORAGE_OPTIONS
    )
    
    # Read QS Rankings Excel
    df_qs = pd.read_excel(
        f"s3://{BRONZE_BUCKET}/2026 QS World University Rankings 1.3 (For qs.com).xlsx",
        storage_options=PANDAS_STORAGE_OPTIONS
    )

    print("Data Cleaning & Transformation...")
    
    # Clean Kaggle Data
    df_kaggle = df_kaggle.fillna('N/A')
    
    # Clean Wikidata
    df_wiki['universityLabel'] = df_wiki['universityLabel'].fillna('Unknown')
    df_wiki['universityLabel'] = df_wiki['universityLabel'].str.strip()
    
    # Process QS Rankings
    # Assuming columns like 'Institution Name' and 'Rank' exist. 
    # Let's standardize the name for joining.
    # Note: Excel columns can be dynamic. We will look for a column that contains 'Institution' or 'Name'
    inst_col = [c for c in df_qs.columns if 'institution' in str(c).lower() or 'name' in str(c).lower()][0]
    rank_col = [c for c in df_qs.columns if 'rank' in str(c).lower()][0]
    
    df_qs_clean = df_qs[[inst_col, rank_col]].copy()
    df_qs_clean.columns = ['universityLabel', 'QS_Rank']
    df_qs_clean['universityLabel'] = df_qs_clean['universityLabel'].astype(str).str.strip()
    
    # Handling non-numeric ranks like "501-510" by taking the first number
    df_qs_clean['QS_Rank_Num'] = df_qs_clean['QS_Rank'].astype(str).str.extract(r'(\d+)').astype(float)
    
    # Merge Wikidata with QS to Flag Top Tier
    df_wiki_enriched = df_wiki.merge(df_qs_clean, on='universityLabel', how='left')
    
    def flag_tier(rank):
        if pd.isna(rank):
            return "Non-Formal / Experience"
        elif rank <= 100:
            return "Top Tier Elite (Top 100)"
        elif rank <= 500:
            return "Mid Tier (101-500)"
        else:
            return "Non-Top Tier (>500)"
            
    df_wiki_enriched['University_Tier_Flag'] = df_wiki_enriched['QS_Rank_Num'].apply(flag_tier)
    
    print("Writing Cleansed Data to Silver Layer (Delta Format)...")
    s3_client = get_s3_client()
    try:
        s3_client.create_bucket(Bucket=SILVER_BUCKET)
    except:
        pass # Bucket might already exist

    # Write Parquet Tables to S3
    df_kaggle.to_parquet(
        f"s3://{SILVER_BUCKET}/unicorn_startups/data.parquet",
        storage_options=PANDAS_STORAGE_OPTIONS,
        engine="pyarrow",
        index=False
    )
    
    df_wiki_enriched.to_parquet(
        f"s3://{SILVER_BUCKET}/executive_profiles/data.parquet",
        storage_options=PANDAS_STORAGE_OPTIONS,
        engine="pyarrow",
        index=False
    )

    print("--- File Format Storage Comparison ---")
    s3 = get_s3_client()
    
    # Bronze Size
    bronze_kaggle = s3.head_object(Bucket=BRONZE_BUCKET, Key='kaggle_unicorn_startups.csv')['ContentLength']
    bronze_wiki = s3.head_object(Bucket=BRONZE_BUCKET, Key='wikidata_executive_profile.csv')['ContentLength']
    bronze_qs = s3.head_object(Bucket=BRONZE_BUCKET, Key='2026 QS World University Rankings 1.3 (For qs.com).xlsx')['ContentLength']
    total_bronze = bronze_kaggle + bronze_wiki + bronze_qs
    
    # Silver Size (Delta/Parquet)
    silver_kaggle = calculate_s3_folder_size(s3, SILVER_BUCKET, 'unicorn_startups/')
    silver_wiki = calculate_s3_folder_size(s3, SILVER_BUCKET, 'executive_profiles/')
    total_silver = silver_kaggle + silver_wiki
    
    print(f"Bronze Layer (Raw CSV/Excel): {total_bronze / 1024:.2f} KB")
    print(f"Silver Layer (Compressed Delta/Parquet): {total_silver / 1024:.2f} KB")
    print(f"Storage Reduction: {((total_bronze - total_silver) / total_bronze) * 100:.2f}%")
    print("Silver Transformation Process Completed.")

if __name__ == "__main__":
    process_silver()
