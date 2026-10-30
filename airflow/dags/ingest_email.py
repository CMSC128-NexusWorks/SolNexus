"""Gmail -> bronze ingestion for the connected SolTech mailbox (SNX-32, scheduled in SNX-33).

All connector logic lives in the solnexus_ingest package (airflow/include). This DAG supplies only
credentials, the database connection, the schedule and failure semantics. It runs hourly (Manila time,
GMAIL_SYNC_SCHEDULE) once unpaused, records each run in app.pipeline_runs, and on success emits the
GMAIL_BRONZE dataset event that starts transform_bronze_to_silver.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.operators.python import get_current_context
from airflow.timetables.trigger import CronTriggerTimetable

from solnexus_ingest.orchestration import GMAIL_BRONZE, SCHEDULE_TIMEZONE, warehouse_conn
from solnexus_ingest.runs import GMAIL_INGEST, airflow_failure_callbacks

# Hourly is the data/API contract's proposed default, pending team approval and quota validation.
SCHEDULE = os.environ.get("GMAIL_SYNC_SCHEDULE") or "0 * * * *"


@dag(
    dag_id="ingest_email",
    description="Incrementally ingest the connected Gmail mailbox into bronze.raw_messages.",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    # CronTriggerTimetable runs at the cron time itself, not at the end of the interval.
    schedule=CronTriggerTimetable(SCHEDULE, timezone=SCHEDULE_TIMEZONE),
    # No backfill of missed hours: one run resumes from the checkpoint and catches up on its own.
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
    @task(
        execution_timeout=timedelta(minutes=30),
        # Emitted even when no new mail arrived: app tables (imports, staff edits) may still have
        # changed, and the silver build is cheap.
        outlets=[GMAIL_BRONZE],
        # Record 'retrying' / 'failed' in app.pipeline_runs, so the failure reaches the dashboard.
        **airflow_failure_callbacks(GMAIL_INGEST),
    )
    def sync_gmail() -> dict[str, int | str]:
        """Sync the mailbox and return per-run counts (no addresses or content, so safe in XCom)."""
        # Imported inside the task so the scheduler's frequent DAG-file parsing stays fast and does
        # not depend on Google/psycopg2 imports succeeding.
        from solnexus_ingest.gmail.client import GmailAuthError, GmailClient, GmailPolicyError
        from solnexus_ingest.gmail.sync import SyncSettings, sync_mailbox
        from solnexus_ingest.runs import mark_running, mark_succeeded

        context = get_current_context()

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

        conn = warehouse_conn()
        try:
            mark_running(conn, GMAIL_INGEST, context["dag"].dag_id, context["run_id"], context["ti"].try_number)
            client = GmailClient.from_token_file(token_file)
            counts = sync_mailbox(client, conn, settings, job_run_id=context["run_id"])
            # sync_mailbox has already committed the pages and checkpoint. If this update fails, the task
            # retries, finds nothing new and records zero counts: an under-count, never a duplicate.
            mark_succeeded(conn, GMAIL_INGEST, context["run_id"], counts, context["ti"].try_number)
            conn.commit()
            return counts
        except (GmailAuthError, GmailPolicyError) as exc:
            # Revoked/expired consent or an admin policy will not fix itself: fail now, visibly,
            # without burning retries. See airflow/README.md for the operator steps. Every other
            # error (exhausted backoff, used-up daily quota, retryable token-endpoint outage) is
            # left to the task's normal retries.
            raise AirflowFailException(f"Gmail needs operator action: {exc}") from exc
        finally:
            conn.close()

    sync_gmail()


ingest_email()
