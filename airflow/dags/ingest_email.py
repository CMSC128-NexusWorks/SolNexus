"""Gmail -> bronze ingestion for the connected SolTech mailbox (SNX-32).

All connector logic lives in the solnexus_ingest package (airflow/include); this DAG only supplies
credentials, the database connection and failure semantics. Scheduling is SNX-33's job, so the DAG
runs on demand until then: trigger it from the UI or with `airflow dags trigger ingest_email`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.operators.python import get_current_context

# Airflow connection to the SolNexus warehouse (set as AIRFLOW_CONN_SOLNEXUS_DB in compose.yaml).
WAREHOUSE_CONN_ID = "solnexus_db"


@dag(
    dag_id="ingest_email",
    description="Incrementally ingest the connected Gmail mailbox into bronze.raw_messages.",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    # Two overlapping runs would read the same checkpoint and race to advance it.
    max_active_runs=1,
    default_args={
        # Covers transient failures that outlast the client's own bounded backoff. Safe because a
        # rerun resumes from the last committed checkpoint and bronze ignores replays.
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    tags=["phase1", "ingestion", "gmail"],
    doc_md=__doc__,
)
def ingest_email():
    @task(execution_timeout=timedelta(minutes=30))
    def sync_gmail() -> dict[str, int | str]:
        """Sync the mailbox and return per-run counts (no addresses or content, so safe in XCom)."""
        # Imported inside the task so the scheduler's frequent DAG-file parsing stays fast and does
        # not depend on Google/psycopg2 imports succeeding.
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        from solnexus_ingest.gmail.client import GmailAuthError, GmailClient, GmailPolicyError
        from solnexus_ingest.gmail.sync import SyncSettings, sync_mailbox

        token_file = os.environ.get("GMAIL_TOKEN_FILE", "/opt/airflow/secrets/gmail-token.json")
        if not os.path.isfile(token_file):
            raise AirflowFailException(
                "Gmail token file not found; authorize the mailbox (backend/spikes/README.md) and mount .secrets"
            )
        settings = SyncSettings(
            # Empty strings from Compose defaults mean "not set".
            label_id=os.environ.get("GMAIL_LABEL_ID") or None,
            backfill_query=os.environ.get("GMAIL_BACKFILL_QUERY") or None,
        )

        conn = PostgresHook(postgres_conn_id=WAREHOUSE_CONN_ID).get_conn()
        try:
            client = GmailClient.from_token_file(token_file)
            return sync_mailbox(client, conn, settings, job_run_id=get_current_context()["run_id"])
        except (GmailAuthError, GmailPolicyError) as exc:
            # Revoked/expired consent or an admin policy will not fix itself: fail now, visibly,
            # without burning retries. See airflow/README.md for the operator steps.
            raise AirflowFailException(f"Gmail needs operator action: {exc}") from exc
        finally:
            conn.close()

    sync_gmail()


ingest_email()
