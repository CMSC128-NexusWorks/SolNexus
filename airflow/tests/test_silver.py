"""Silver publication: the swap is all-or-nothing and only a complete build becomes live.

These tests create and drop the silver schemas, so they need the throwaway *_ingest_test database
(conftest.db), never a database the dashboard reads. dbt itself is not run here; see airflow/README.md
for the end-to-end check.
"""

from __future__ import annotations

import copy
import os
import pickle
import uuid

import psycopg2
import pytest

from solnexus_ingest.runs import SILVER_PUBLISH, mark_running
from solnexus_ingest.silver import (
    BUILD_LOCK_KEY,
    BUILD_SCHEMA,
    BuildInProgressError,
    DbtBuildError,
    StaleBuildError,
    build,
    publish,
    reset_build_schema,
    stamp_build,
    summarize_run_results,
)


def execute(db, statement, params=None):
    with db.cursor() as cur:
        cur.execute(statement, params)
        rows = cur.fetchall() if cur.description else None
    db.commit()
    return rows


def make_schema(db, schema, marker, tables=("interactions", "leads")):
    """A stand-in for a dbt build: each table holds one row naming which build produced it."""
    execute(db, f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    execute(db, f"CREATE SCHEMA {schema}")
    for table in tables:
        execute(db, f"CREATE TABLE {schema}.{table} AS SELECT %s::text AS built_by", (marker,))


def live_marker(db):
    return execute(db, "SELECT built_by FROM silver.leads")[0][0]


def run_status(db, run_id):
    return execute(
        db,
        "SELECT status, counts FROM app.pipeline_runs WHERE pipeline = %s AND airflow_run_id = %s",
        (SILVER_PUBLISH, run_id),
    )[0]


@pytest.fixture
def run_id(db) -> str:
    rid = f"test__{uuid.uuid4().hex}"
    mark_running(db, SILVER_PUBLISH, "transform_bronze_to_silver", rid, attempt=1)
    return rid


@pytest.fixture
def live_silver(db):
    make_schema(db, "silver", "old")
    yield
    execute(db, f"DROP SCHEMA IF EXISTS {BUILD_SCHEMA} CASCADE")


def test_complete_build_replaces_live_silver_and_marks_success(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "new")
    stamp_build(db, run_id)

    counts = publish(db, run_id, {"success": 2, "pass": 5}, attempt=1)

    assert live_marker(db) == "new"
    assert counts == {"dbt_success": 2, "dbt_pass": 5, "interactions_rows": 1, "leads_rows": 1}
    assert run_status(db, run_id) == ("succeeded", counts)
    assert execute(db, "SELECT count(*) FROM pg_namespace WHERE nspname IN ('silver_build', 'silver_previous')")[0][0] == 0


def test_incomplete_build_cannot_be_stamped(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "new", tables=("interactions",))

    with pytest.raises(StaleBuildError, match="missing"):
        stamp_build(db, run_id)
    db.rollback()


def test_unstamped_build_keeps_old_silver_and_does_not_mark_fresh(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "manual-or-failed")

    with pytest.raises(StaleBuildError, match="not this run"):
        publish(db, run_id, {}, attempt=1)

    assert live_marker(db) == "old"
    assert run_status(db, run_id)[0] == "running"


def test_another_runs_build_is_not_published(db, live_silver, run_id):
    # Run A's publish retried late, after run B rebuilt silver_build.
    make_schema(db, BUILD_SCHEMA, "run-b")
    stamp_build(db, "some-other-run")

    with pytest.raises(StaleBuildError, match="not this run"):
        publish(db, run_id, {}, attempt=2)

    assert live_marker(db) == "old"


def test_tables_replaced_after_the_stamp_are_not_published(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "passed")
    stamp_build(db, run_id)
    # A later dbt build into silver_build replaces the tables (new OIDs) but keeps the schema comment.
    execute(db, f"DROP TABLE {BUILD_SCHEMA}.leads")
    execute(db, f"CREATE TABLE {BUILD_SCHEMA}.leads AS SELECT 'failed-tests'::text AS built_by")

    with pytest.raises(StaleBuildError, match="changed"):
        publish(db, run_id, {}, attempt=1)

    assert live_marker(db) == "old"


def test_failed_build_is_dropped_and_its_error_kept(db, run_id):
    def failing_dbt():
        make_schema(db, BUILD_SCHEMA, "half-built")
        raise DbtBuildError(returncode=1, failed_nodes=["test.solnexus.t0"], tests_only=True)

    with pytest.raises(DbtBuildError):
        build(db, run_id, failing_dbt)

    assert execute(db, "SELECT count(*) FROM pg_namespace WHERE nspname = %s", (BUILD_SCHEMA,))[0][0] == 0


def test_passing_build_is_stamped_for_its_run(db, live_silver, run_id):
    counts = build(db, run_id, lambda: make_schema(db, BUILD_SCHEMA, "built") or {"pass": 3})

    assert counts == {"pass": 3}
    publish(db, run_id, counts, attempt=1)
    assert live_marker(db) == "built"


def test_first_publication_works_without_a_live_schema(db, run_id):
    execute(db, "DROP SCHEMA IF EXISTS silver CASCADE")
    make_schema(db, BUILD_SCHEMA, "first")
    stamp_build(db, run_id)

    publish(db, run_id, {}, attempt=1)

    assert live_marker(db) == "first"


def test_reset_drops_a_leftover_build(db):
    make_schema(db, BUILD_SCHEMA, "stale")

    reset_build_schema(db)

    assert execute(db, "SELECT count(*) FROM pg_namespace WHERE nspname = %s", (BUILD_SCHEMA,))[0][0] == 0


def test_build_error_message_names_nodes_only():
    error = DbtBuildError(returncode=1, failed_nodes=[f"test.solnexus.t{i}" for i in range(7)], tests_only=True)

    assert str(error) == (
        "dbt build failed on 7 node(s): test.solnexus.t0, test.solnexus.t1, test.solnexus.t2, "
        "test.solnexus.t3, test.solnexus.t4 (+2 more)"
    )
    assert "before reporting" in str(DbtBuildError(returncode=2))


def test_run_results_are_counted_by_status():
    results = [{"status": "success"}, {"status": "pass"}, {"status": "pass"}, {"status": "fail"}]

    assert summarize_run_results(results) == {"success": 1, "pass": 2, "fail": 1}


def test_build_error_survives_pickle_copy_and_hashing():
    error = DbtBuildError(returncode=1, failed_nodes=["test.solnexus.t0"], tests_only=True)

    for clone in (pickle.loads(pickle.dumps(error)), copy.copy(error)):
        assert (clone.returncode, clone.failed_nodes, clone.tests_only) == (1, ["test.solnexus.t0"], True)
        assert str(clone) == str(error)
    assert hash(error)


class _DeadConnection:
    """Stands in for a connection the database dropped mid-swap."""

    def cursor(self):
        raise psycopg2.OperationalError("server closed the connection unexpectedly")

    def rollback(self):
        raise psycopg2.InterfaceError("connection already closed")


def test_publish_reraises_the_original_error_when_rollback_also_fails():
    with pytest.raises(psycopg2.OperationalError, match="server closed"):
        publish(_DeadConnection(), "test-run", {}, attempt=1)


def test_a_rerun_after_publication_swaps_nothing(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "new")
    stamp_build(db, run_id)
    first = publish(db, run_id, {"pass": 5}, attempt=1)
    make_schema(db, BUILD_SCHEMA, "someone-elses-build")

    assert publish(db, run_id, {"pass": 1}, attempt=1) == first
    assert live_marker(db) == "new"
    assert run_status(db, run_id) == ("succeeded", first)


@pytest.fixture
def other_session_holding_the_build_lock(db):
    other = psycopg2.connect(os.environ["SOLNEXUS_TEST_DATABASE_URL"])
    with other.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (BUILD_LOCK_KEY,))
    yield
    other.close()  # releases the lock


def test_build_refuses_to_start_while_another_holds_the_lock(db, run_id, other_session_holding_the_build_lock):
    with pytest.raises(BuildInProgressError):
        build(db, run_id, lambda: pytest.fail("dbt must not run"))


def test_publish_waits_for_the_lock_and_then_gives_up_untouched(
    db, live_silver, run_id, other_session_holding_the_build_lock
):
    make_schema(db, BUILD_SCHEMA, "new")
    stamp_build(db, run_id)

    with pytest.raises(psycopg2.errors.LockNotAvailable):
        publish(db, run_id, {}, attempt=1, lock_timeout="100ms")

    assert live_marker(db) == "old"


def test_build_releases_the_lock_when_done(db, run_id):
    build(db, run_id, lambda: make_schema(db, BUILD_SCHEMA, "built") or {})

    other = psycopg2.connect(os.environ["SOLNEXUS_TEST_DATABASE_URL"])
    try:
        with other.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (BUILD_LOCK_KEY,))
            assert cur.fetchone()[0] is True
    finally:
        other.close()
    reset_build_schema(db)
