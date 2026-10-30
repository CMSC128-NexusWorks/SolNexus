"""Run-status recording: safe error summaries and the app.pipeline_runs state transitions."""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from solnexus_ingest.runs import (
    ERROR_SUMMARY_MAX,
    GMAIL_INGEST,
    mark_running,
    mark_succeeded,
    mark_unfinished,
    succeeded_counts,
    summarize_error,
)

DAG = "ingest_email"


def test_postgres_errors_keep_only_class_sqlstate_and_constraint(db):
    # Even the primary message quotes the rejected value; it must not reach the dashboard.
    with pytest.raises(psycopg2.Error) as caught:
        with db.cursor() as cur:
            cur.execute("SELECT %s::uuid", ("lead-a@example.test",))
    db.rollback()

    assert summarize_error(caught.value) == "InvalidTextRepresentation (SQLSTATE 22P02)"


def test_postgres_constraint_errors_name_the_constraint(db):
    with pytest.raises(psycopg2.Error) as caught:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO app.pipeline_runs (pipeline, dag_id, airflow_run_id, status) VALUES ('nope', 'd', 'r', 'running')"
            )
    db.rollback()

    assert summarize_error(caught.value) == "CheckViolation (SQLSTATE 23514, constraint pipeline_runs_pipeline_check)"


def test_other_errors_keep_their_first_line_with_quoted_values_masked():
    exc = PermissionError("[Errno 13] Permission denied: '/opt/airflow/secrets/gmail-token.json'\nmore")

    assert summarize_error(exc) == "PermissionError: [Errno 13] Permission denied: <redacted>"
    assert summarize_error(KeyError("lead-a@example.test")) == "KeyError: <redacted>"
    # Connector messages carry no quotes, so they stay readable.
    assert summarize_error(RuntimeError("gave up after 5 retries (403 rateLimitExceeded)")) == (
        "RuntimeError: gave up after 5 retries (403 rateLimitExceeded)"
    )


def test_summary_handles_empty_and_long_messages():
    assert summarize_error(TimeoutError()) == "TimeoutError"
    assert summarize_error(psycopg2.InterfaceError("connection already closed")) == "InterfaceError"
    assert len(summarize_error(RuntimeError("x" * 1000))) == ERROR_SUMMARY_MAX
    assert summarize_error(None) is None


@pytest.fixture
def run_id() -> str:
    return f"test__{uuid.uuid4().hex}"


def run_row(db, run_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT status, attempt, finished_at IS NOT NULL, counts, error_summary, dag_id "
            "FROM app.pipeline_runs WHERE pipeline = %s AND airflow_run_id = %s",
            (GMAIL_INGEST, run_id),
        )
        row = cur.fetchone()
    db.commit()
    return row


def test_retry_then_success_ends_as_one_succeeded_row(db, run_id):
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=1)
    mark_unfinished(db, GMAIL_INGEST, DAG, run_id, will_retry=True, error=TimeoutError("Gmail call timed out"))
    assert run_row(db, run_id)[:3] == ("retrying", 1, False)

    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=2)
    mark_succeeded(db, GMAIL_INGEST, run_id, {"inserted": 3})
    db.commit()

    assert run_row(db, run_id) == ("succeeded", 2, True, {"inserted": 3}, None, DAG)


def test_final_failure_is_visible_with_its_summary(db, run_id):
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=3)
    mark_unfinished(db, GMAIL_INGEST, DAG, run_id, will_retry=False, error=RuntimeError("gave up after 5 retries"))

    assert run_row(db, run_id)[:3] == ("failed", 3, True)
    assert run_row(db, run_id)[4] == "RuntimeError: gave up after 5 retries"


def test_failure_before_the_run_row_exists_is_still_recorded(db, run_id):
    mark_unfinished(db, GMAIL_INGEST, DAG, run_id, will_retry=False, error=FileNotFoundError("token missing"))

    assert run_row(db, run_id)[0] == "failed"


def test_success_is_not_visible_until_the_caller_commits(db, run_id):
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=1)
    mark_succeeded(db, GMAIL_INGEST, run_id, {})
    db.rollback()  # the work it reported did not commit, so neither does the success

    assert run_row(db, run_id)[0] == "running"


def test_success_without_a_running_row_is_a_wiring_error(db, run_id):
    with pytest.raises(RuntimeError, match="mark_running"):
        mark_succeeded(db, GMAIL_INGEST, run_id, {})
    db.rollback()


def test_status_view_reports_the_latest_run_and_last_success(db, run_id):
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=1)
    mark_succeeded(db, GMAIL_INGEST, run_id, {"inserted": 1})
    db.commit()
    later = f"{run_id}-later"
    mark_running(db, GMAIL_INGEST, DAG, later, attempt=1)
    mark_unfinished(db, GMAIL_INGEST, DAG, later, will_retry=False, error=RuntimeError("boom"))

    with db.cursor() as cur:
        cur.execute(
            "SELECT last_run_status, last_succeeded_at IS NOT NULL FROM app.pipeline_status WHERE pipeline = %s",
            (GMAIL_INGEST,),
        )
        status, has_success = cur.fetchone()
    db.commit()
    # The shared test database also holds other tests' runs, so only check what this test controls.
    assert status == "failed"
    assert has_success


def test_a_succeeded_run_is_never_moved_back(db, run_id):
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=1)
    mark_succeeded(db, GMAIL_INGEST, run_id, {"inserted": 3})
    db.commit()

    # An operator clears the finished task, or its retry runs after the commit.
    mark_running(db, GMAIL_INGEST, DAG, run_id, attempt=2)
    mark_unfinished(db, GMAIL_INGEST, DAG, run_id, will_retry=False, error=RuntimeError("boom"))
    mark_succeeded(db, GMAIL_INGEST, run_id, {"inserted": 0})
    db.commit()

    assert run_row(db, run_id)[:5] == ("succeeded", 1, True, {"inserted": 3}, None)
    assert succeeded_counts(db, GMAIL_INGEST, run_id) == {"inserted": 3}
