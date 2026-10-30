"""dbt bronze/app -> silver build and atomic publication (SNX-33).

Runs after every successful ingest_email run (GMAIL_BRONZE dataset), and also hourly at :30 Manila time
(SILVER_REFRESH_SCHEDULE). The hourly run means spreadsheet imports and staff edits in app.* reach
silver even while Gmail ingestion is down, e.g. waiting for re-consent.

build_silver runs `dbt build` into silver_build. publish_silver swaps that schema in and marks the run
'succeeded' in one transaction (solnexus_ingest.silver). A failed build or failed dbt test leaves the
previous silver tables and published_at as they were, and the run shows 'failed' in
app.pipeline_status and the Airflow UI.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.operators.python import get_current_context
from airflow.timetables.datasets import DatasetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from solnexus_ingest.orchestration import GMAIL_BRONZE, SCHEDULE_TIMEZONE, WAREHOUSE_CONN_ID
from solnexus_ingest.runs import SILVER_PUBLISH, airflow_failure_callbacks

DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR") or "/opt/airflow/dbt"
# Offset from ingest_email's :00, so the fallback does not start next to a dataset-triggered run.
FALLBACK_SCHEDULE = os.environ.get("SILVER_REFRESH_SCHEDULE") or "30 * * * *"

callbacks = airflow_failure_callbacks(SILVER_PUBLISH, WAREHOUSE_CONN_ID)


def _warehouse_conn():
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    return PostgresHook(postgres_conn_id=WAREHOUSE_CONN_ID).get_conn()


@dag(
    dag_id="transform_bronze_to_silver",
    description="Build silver with dbt in a staging schema and publish it atomically.",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=DatasetOrTimeSchedule(
        timetable=CronTriggerTimetable(FALLBACK_SCHEDULE, timezone=SCHEDULE_TIMEZONE),
        datasets=[GMAIL_BRONZE],
    ),
    catchup=False,
    # Two runs would build into and swap the same staging schema. Later triggers queue instead.
    max_active_runs=1,
    default_args={
        # For transient failures (database restart, lock timeout during the swap). A failed dbt test
        # fails at once instead (see build_silver), because rebuilding the same data cannot fix it.
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
    },
    tags=["phase1", "transform", "dbt"],
    doc_md=__doc__,
)
def transform_bronze_to_silver():
    @task(execution_timeout=timedelta(minutes=30), **callbacks)
    def build_silver() -> dict[str, int]:
        """Run dbt build into silver_build; return dbt node counts by status."""
        from solnexus_ingest.runs import mark_running
        from solnexus_ingest.silver import DbtBuildError, reset_build_schema, run_dbt_build

        context = get_current_context()
        conn = _warehouse_conn()
        try:
            mark_running(conn, SILVER_PUBLISH, context["dag"].dag_id, context["run_id"], context["ti"].try_number)
            reset_build_schema(conn)
        finally:
            conn.close()
        try:
            return run_dbt_build(DBT_PROJECT_DIR)
        except DbtBuildError as exc:
            if exc.tests_only:
                # The data broke a silver contract test. Retrying rebuilds the same data, so fail now
                # and leave the run visibly failed for an operator (airflow/README.md).
                raise AirflowFailException(str(exc)) from exc
            raise

    @task(execution_timeout=timedelta(minutes=5), **callbacks)
    def publish_silver(build_counts: dict[str, int]) -> dict[str, int]:
        """Swap silver_build in as silver and record the publication."""
        from solnexus_ingest.runs import mark_running
        from solnexus_ingest.silver import publish

        context = get_current_context()
        conn = _warehouse_conn()
        try:
            # Back to 'running' in case this task is a retry after a failed swap.
            mark_running(conn, SILVER_PUBLISH, context["dag"].dag_id, context["run_id"], context["ti"].try_number)
            return publish(conn, context["run_id"], build_counts)
        finally:
            conn.close()

    publish_silver(build_silver())


transform_bronze_to_silver()
