import os
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. Your exact key path
KEY_PATH = r"C:\Users\mishi\OneDrive\Desktop\voice_to_bq_project\ba882-team4-474802-dedd2ec99f90.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

def get_bq_client():
    """Generates a fresh, fully authenticated client per request to prevent 401 errors on retries."""
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

def execute_bq_query(sql_query: str):
    """Executes SQL safely with a higher guardrail for global GitHub queries."""
    try:
        # Get a fresh client for this specific attempt
        client = get_bq_client()

        # STEP 1: Dry run for cost safety
        dry_run_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_job = client.query(sql_query, job_config=dry_run_config)
        
        gb_scanned = dry_job.total_bytes_processed / 1e9
        
        # STEP 2: The New Guardrail (Raised to 150 GB)
        # Note: You have 1,000 GB (1TB) of free tier scanning per month from Google.
        if gb_scanned > 150.0: 
            raise Exception(f"Query too expensive! ({gb_scanned:.2f} GB scanned). Ask a more specific question.")

        # STEP 3: Real execution
        query_job = client.query(sql_query)
        results = query_job.result()
        return [dict(row) for row in results]

    except Exception as e:
        # Pass the error back up to app.py for self-healing
        raise e