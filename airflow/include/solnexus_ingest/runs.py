"""Record pipeline run status in app.pipeline_runs (SNX-33).

One row per (pipeline, Airflow run_id). A task marks it 'running' when it starts. Task callbacks
mark it 'retrying' or 'failed'. The last task marks it 'succeeded', in the same transaction as the
work it reports: the checkpoint commit is already durable for Gmail, and the schema swap for silver.
Airflow's UI stays the operator's detailed view. This table is the small, stable summary the API
reads for the dashboard (app.pipeline_status).

Error summaries keep only the exception class and the first line of its message. Connector errors
are written to be safe (status codes, Google reasons, counts). The first line also leaves out
psycopg2's DETAIL line, which can quote row values. Full tracebacks stay in the Airflow task log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from psycopg2.extensions import connection as Connection
from psycopg2.extras import Json

log = logging.getLogger(__name__)

GMAIL_INGEST = "gmail_ingest"
SILVER_PUBLISH = "silver_publish"

ERROR_SUMMARY_MAX = 300


def summarize_error(exc: BaseException | None) -> str | None:
    """Exception class plus the first line of its message, truncated."""
    if exc is None:
        return None
    first_line = (str(exc).strip().splitlines() or [""])[0]
    summary = f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__
    return summary[:ERROR_SUMMARY_MAX]


def mark_running(conn: Connection, pipeline: str, dag_id: str, airflow_run_id: str, attempt: int) -> None:
    """Create the run row, or reset it for a retry or a cleared rerun. Commits."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.pipeline_runs (pipeline, dag_id, airflow_run_id, status, attempt)
            VALUES (%s, %s, %s, 'running', %s)
            ON CONFLICT (pipeline, airflow_run_id) DO UPDATE
               SET status = 'running', attempt = EXCLUDED.attempt, finished_at = NULL, error_summary = NULL
            """,
            (pipeline, dag_id, airflow_run_id, attempt),
        )
    conn.commit()


def mark_succeeded(conn: Connection, pipeline: str, airflow_run_id: str, counts: Mapping[str, Any]) -> None:
    """Mark the run succeeded. Does NOT commit, so the caller can commit it with the work it reports."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE app.pipeline_runs
               SET status = 'succeeded', finished_at = now(), counts = %s, error_summary = NULL
             WHERE pipeline = %s AND airflow_run_id = %s
            """,
            (Json(dict(counts)), pipeline, airflow_run_id),
        )
        if cur.rowcount != 1:
            # mark_running always runs first in the same DAG run, so a missing row is a wiring bug.
            raise RuntimeError(f"no {pipeline} run row for this Airflow run; was mark_running called?")


def mark_unfinished(
    conn: Connection,
    pipeline: str,
    dag_id: str,
    airflow_run_id: str,
    *,
    will_retry: bool,
    error: BaseException | None,
) -> None:
    """Mark the run 'retrying' or 'failed' with a safe error summary. Commits.

    Upserts in case the failure happened before mark_running could write the row, e.g. the token file
    was missing or the warehouse was briefly unreachable at task start.
    """
    status = "retrying" if will_retry else "failed"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.pipeline_runs (pipeline, dag_id, airflow_run_id, status, finished_at, error_summary)
            VALUES (%s, %s, %s, %s, CASE WHEN %s = 'failed' THEN now() END, %s)
            ON CONFLICT (pipeline, airflow_run_id) DO UPDATE
               SET status = EXCLUDED.status, finished_at = EXCLUDED.finished_at,
                   error_summary = EXCLUDED.error_summary
            """,
            (pipeline, dag_id, airflow_run_id, status, status, summarize_error(error)),
        )
    conn.commit()


def airflow_failure_callbacks(pipeline: str, conn_id: str) -> dict[str, Callable[[dict], None]]:
    """on_retry_callback / on_failure_callback task arguments that record the run's state.

    The callbacks run after the task's exception, in the task's own process. They must never raise:
    a callback error would only hide the real failure in the log, and the run row is a summary.
    """

    def record(context: dict, will_retry: bool) -> None:
        try:
            # Imported lazily so the DAG files parse without the Postgres provider loaded.
            from airflow.providers.postgres.hooks.postgres import PostgresHook

            conn = PostgresHook(postgres_conn_id=conn_id).get_conn()
            try:
                mark_unfinished(
                    conn,
                    pipeline,
                    context["dag"].dag_id,
                    context["run_id"],
                    will_retry=will_retry,
                    error=context.get("exception"),
                )
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - see docstring
            log.exception("could not record %s run status", pipeline)

    return {
        "on_retry_callback": lambda context: record(context, will_retry=True),
        "on_failure_callback": lambda context: record(context, will_retry=False),
    }
