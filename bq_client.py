import os
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest
from rich.console import Console

console = Console()

# Point to your downloaded GCP service account key
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\mishi\Downloads\ba882-team4-474802-bee53a65f2ac.json"

client = bigquery.Client()

def execute_bq_query(sql_query: str):
    """Executes SQL on BigQuery and returns a list of dictionaries."""
    try:
        query_job = client.query(sql_query)
        results = query_job.result() 
        return [dict(row) for row in results]
    except BadRequest as e:
        # We raise this specific error to trigger the self-healing loop in main.py
        raise e
    except Exception as e:
        console.print(f"[bold red]Critical Database Error: {e}[/]")
        raise e