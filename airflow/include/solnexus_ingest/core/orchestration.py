"""Names the DAGs share (SNX-33).

They live here, not in a DAG file, because importing one DAG file from another would also define
that file's DAG while the second file is parsed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from airflow.datasets import Dataset

if TYPE_CHECKING:
    from psycopg2.extensions import connection as Connection

# Airflow connection to the SolNexus warehouse (set as AIRFLOW_CONN_SOLNEXUS_DB in compose.yaml).
WAREHOUSE_CONN_ID = "solnexus_db"


def warehouse_conn() -> Connection:
    """Open a psycopg2 connection to the warehouse. Every task and callback connects through here.

    The hook is imported lazily so that parsing a DAG file does not load the Postgres provider.
    """
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    return PostgresHook(postgres_conn_id=WAREHOUSE_CONN_ID).get_conn()


# ingest_email emits this after each successful sync, and transform_bronze_to_silver is scheduled on it.
# It uses a custom scheme so Airflow does not try to validate it as a real Postgres URI.
GMAIL_BRONZE = Dataset("solnexus://bronze/raw_messages/gmail")

# Schedules are crons in Manila time, so they read the way SolTech staff talk about them.
SCHEDULE_TIMEZONE = "Asia/Manila"
