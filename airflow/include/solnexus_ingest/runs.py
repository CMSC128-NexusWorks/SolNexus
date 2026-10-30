"""Record pipeline run status in app.pipeline_runs (SNX-33).

One row per (pipeline, Airflow run_id). A task marks it 'running' when it starts. Task callbacks
mark it 'retrying' or 'failed'. The last task marks it 'succeeded', in the same transaction as the
work it reports: the checkpoint commit is already durable for Gmail, and the schema swap for silver.
A 'succeeded' row is final: no later write moves it back. Otherwise an operator clearing a finished task,
or a retry after a commit whose task then died, would rewrite a real publication as 'running' or
'failed', and published_at would move backwards while the published data stayed live.
Airflow's UI stays the operator's detailed view. This table is the small, stable summary the API
reads for the dashboard (app.pipeline_status).

Error summaries reach the dashboard, so they must never carry record values. A PostgreSQL error is
reduced to its class, SQLSTATE and constraint name: even its primary message can quote the rejected
value (`invalid input syntax for type uuid: "..."`). Any other error keeps its class and first line,
with quoted text masked, because messages like FileNotFoundError's or KeyError's quote their subject.
Connector errors are written without quotes (status codes, Google reasons, dbt node IDs), so they stay
readable. Full tracebacks stay in the Airflow task log.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extras import Json

log = logging.getLogger(__name__)

GMAIL_INGEST = "gmail_ingest"
SILVER_PUBLISH = "silver_publish"

ERROR_SUMMARY_MAX = 300
# A single- or double-quoted span, the usual way exception messages embed the value they choke on.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def summarize_error(exc: BaseException | None) -> str | None:
    """A dashboard-safe one-line summary: see the module docstring for what is kept."""
    if exc is None:
        return None
    name = type(exc).__name__
    if isinstance(exc, psycopg2.Error):
        parts = [f"SQLSTATE {exc.pgcode}"] if exc.pgcode else []
        constraint = getattr(exc.diag, "constraint_name", None)
        if constraint:
            parts.append(f"constraint {constraint}")
        return f"{name} ({', '.join(parts)})" if parts else name
    first_line = (str(exc).strip().splitlines() or [""])[0]
    first_line = _QUOTED.sub("<redacted>", first_line)
    summary = f"{name}: {first_line}" if first_line else name
    return summary[:ERROR_SUMMARY_MAX]


def succeeded_counts(conn: Connection, pipeline: str, airflow_run_id: str) -> dict[str, Any] | None:
    """The recorded counts if this run already succeeded, else None. Does not commit."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT counts FROM app.pipeline_runs WHERE pipeline = %s AND airflow_run_id = %s AND status = 'succeeded'",
            (pipeline, airflow_run_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def mark_running(conn: Connection, pipeline: str, dag_id: str, airflow_run_id: str, attempt: int) -> None:
    """Create the run row, or reset it for a retry. Leaves a succeeded row as it is. Commits."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.pipeline_runs (pipeline, dag_id, airflow_run_id, status, attempt)
            VALUES (%s, %s, %s, 'running', %s)
            ON CONFLICT (pipeline, airflow_run_id) DO UPDATE
               SET status = 'running', attempt = EXCLUDED.attempt, finished_at = NULL, error_summary = NULL
             WHERE app.pipeline_runs.status <> 'succeeded'
            """,
            (pipeline, dag_id, airflow_run_id, attempt),
        )
    conn.commit()


def mark_succeeded(conn: Connection, pipeline: str, airflow_run_id: str, counts: Mapping[str, Any]) -> None:
    """Mark the run succeeded. Does NOT commit, so the caller can commit it with the work it reports.

    If the run already succeeded (a cleared rerun), the first success and its counts are kept.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE app.pipeline_runs
               SET status = 'succeeded', finished_at = now(), counts = %s, error_summary = NULL
             WHERE pipeline = %s AND airflow_run_id = %s AND status <> 'succeeded'
            """,
            (Json(dict(counts)), pipeline, airflow_run_id),
        )
        if cur.rowcount == 0 and succeeded_counts(conn, pipeline, airflow_run_id) is None:
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
    """Mark the run 'retrying' or 'failed' with a safe error summary. Leaves a succeeded row. Commits.

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
             WHERE app.pipeline_runs.status <> 'succeeded'
            """,
            (pipeline, dag_id, airflow_run_id, status, status, summarize_error(error)),
        )
    conn.commit()


def airflow_failure_callbacks(pipeline: str) -> dict[str, Callable[[dict], None]]:
    """on_retry_callback / on_failure_callback task arguments that record the run's state.

    The callbacks run after the task's exception, in the task's own process. They must never raise:
    a callback error would only hide the real failure in the log, and the run row is a summary.
    """

    def record(context: dict, will_retry: bool) -> None:
        try:
            from solnexus_ingest.orchestration import warehouse_conn

            conn = warehouse_conn()
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
