"""Names the DAGs share (SNX-33).

They live here, not in a DAG file, because importing one DAG file from another would also define
that file's DAG while the second file is parsed.
"""

from airflow.datasets import Dataset

# Airflow connection to the SolNexus warehouse (set as AIRFLOW_CONN_SOLNEXUS_DB in compose.yaml).
WAREHOUSE_CONN_ID = "solnexus_db"

# ingest_email emits this after each successful sync, and transform_bronze_to_silver is scheduled on it.
# It uses a custom scheme so Airflow does not try to validate it as a real Postgres URI.
GMAIL_BRONZE = Dataset("solnexus://bronze/raw_messages/gmail")

# Schedules are crons in Manila time, so they read the way SolTech staff talk about them.
SCHEDULE_TIMEZONE = "Asia/Manila"
