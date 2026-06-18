import os
import hashlib
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone

# MinIO Configuration
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
BRONZE_BUCKET = "bronze"

def get_md5(file_path):
    """Calculate MD5 hash of a local file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name='us-east-1' # Default for MinIO
    )

def ensure_bucket_exists(s3_client, bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"Creating bucket: {bucket_name}")
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            raise

def upload_to_bronze(s3_client, file_path, object_name):
    """Uploads file to Bronze layer with Idempotency check and Custom Metadata."""
    local_md5 = get_md5(file_path)
    
    # Check if object exists and compare e-Tag
    try:
        response = s3_client.head_object(Bucket=BRONZE_BUCKET, Key=object_name)
        s3_etag = response['ETag'].strip('"')
        
        if s3_etag == local_md5:
            print(f"[{object_name}] SKIP: File has not changed (MD5 matches E-Tag: {local_md5})")
            return
        else:
            print(f"[{object_name}] UPDATE: File changed. Local MD5: {local_md5}, S3 E-Tag: {s3_etag}")
            
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"[{object_name}] NEW: File not found in MinIO. Uploading...")
        else:
            raise

    # Upload with Custom Metadata
    metadata = {
        'ingestion_timestamp': datetime.now(timezone.utc).isoformat(),
        'source_system': 'local_file_system',
        'operator_id': 'data_engineer_fp',
        'original_md5': local_md5
    }
    
    print(f"[{object_name}] Uploading to {BRONZE_BUCKET}...")
    s3_client.upload_file(
        file_path, 
        BRONZE_BUCKET, 
        object_name,
        ExtraArgs={'Metadata': metadata}
    )
    print(f"[{object_name}] SUCCESS: Uploaded with metadata: {metadata}")

def main():
    files_to_ingest = [
        "kaggle_unicorn_startups.csv",
        "wikidata_executive_profile.csv",
        "2026 QS World University Rankings 1.3 (For qs.com).xlsx"
    ]
    
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, BRONZE_BUCKET)
    
    print("Starting Advanced Ingestion to Bronze Layer...")
    for file_name in files_to_ingest:
        if os.path.exists(file_name):
            upload_to_bronze(s3_client, file_name, file_name)
        else:
            print(f"WARNING: File {file_name} not found locally. Skipping.")
            
    print("Ingestion Process Completed.")

if __name__ == "__main__":
    main()
