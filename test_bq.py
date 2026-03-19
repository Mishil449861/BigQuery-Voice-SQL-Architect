import bq_client
from rich.console import Console

console = Console()

test_sql = """
SELECT repo_name, watch_count 
FROM `bigquery-public-data.github_repos.sample_repos` 
ORDER BY watch_count DESC 
LIMIT 3
"""

console.print("[yellow]Testing connection to Google BigQuery...[/]")

try:
    results = bq_client.execute_bq_query(test_sql)
    console.print("[bold green]Success! Connected to GCP. Here are the top repos:[/]")
    console.print(results)
except Exception as e:
    console.print(f"[bold red]Uh oh, connection failed:[/] {e}")