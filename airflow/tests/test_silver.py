"""Silver publication: the swap is all-or-nothing and only a complete build becomes live.

These tests create and drop the silver schemas, so they need the throwaway *_ingest_test database
(conftest.db), never a database the dashboard reads. dbt itself is not run here; see airflow/README.md
for the end-to-end check.
"""

from __future__ import annotations

import uuid

import pytest

from solnexus_ingest.runs import SILVER_PUBLISH, mark_running
from solnexus_ingest.silver import (
    BUILD_SCHEMA,
    DbtBuildError,
    publish,
    reset_build_schema,
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

    counts = publish(db, run_id, {"success": 2, "pass": 5})

    assert live_marker(db) == "new"
    assert counts == {"dbt_success": 2, "dbt_pass": 5, "interactions_rows": 1, "leads_rows": 1}
    assert run_status(db, run_id) == ("succeeded", counts)
    assert execute(db, "SELECT count(*) FROM pg_namespace WHERE nspname IN ('silver_build', 'silver_previous')")[0][0] == 0


def test_incomplete_build_keeps_old_silver_and_does_not_mark_fresh(db, live_silver, run_id):
    make_schema(db, BUILD_SCHEMA, "new", tables=("interactions",))

    with pytest.raises(RuntimeError, match="missing"):
        publish(db, run_id, {})

    assert live_marker(db) == "old"
    assert run_status(db, run_id)[0] == "running"


def test_first_publication_works_without_a_live_schema(db, run_id):
    execute(db, "DROP SCHEMA IF EXISTS silver CASCADE")
    make_schema(db, BUILD_SCHEMA, "first")

    publish(db, run_id, {})

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
