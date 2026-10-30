"""Build silver with dbt in a staging schema and publish it atomically (SNX-33).

Why a staging schema: `dbt build` replaces each model and then tests it. Run against silver directly,
a failing test on silver.interactions would leave the new, bad table live, and dbt would skip
silver.leads, so the two would no longer match. Instead dbt builds everything into silver_build, and
publish() swaps that schema in only after the whole build passed. The swap and the 'succeeded' run row
commit in one transaction. So a failed build or swap leaves the previous silver, and the previous
published_at, exactly as they were (data/API contract: "a failed run must not claim a fresh
publication").

Only this run's passing build is published. silver_build is shared by every run, so a build that
passed is stamped with a schema comment naming its Airflow run and the OIDs of its tables. publish()
refuses a build whose stamp names another run or whose tables changed since (a later failed build, or
a manual `dbt build` into silver_build, replaces the tables and so changes their OIDs). A failed build
drops silver_build at once, so its tables never wait around to be swapped in.

Builds and swaps also hold one PostgreSQL advisory lock (BUILD_LOCK_KEY), so two of them never touch
silver_build at once, even when an operator runs `airflow dags test` beside the scheduler, which
max_active_runs does not cover. Manual dbt runs must use another schema (airflow/README.md).

dbt owns only the silver tables (dbt_project.yml). Nothing outside silver may depend on them, because
the swap drops the previous schema with CASCADE.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as Connection

from solnexus_ingest.runs import SILVER_PUBLISH, mark_succeeded, succeeded_counts

log = logging.getLogger(__name__)

LIVE_SCHEMA = "silver"
BUILD_SCHEMA = "silver_build"
PREVIOUS_SCHEMA = "silver_previous"
# Published relations the API reads. A build missing one of them is never swapped in.
REQUIRED_TABLES = ("interactions", "leads")
# Long enough for in-flight API reads to finish, short enough that a stuck reader fails the task
# (which Airflow retries) instead of hanging it.
SWAP_LOCK_TIMEOUT = "30s"
# Advisory lock held by every build (whole session) and swap (its transaction). Any constant works as
# long as nothing else in the database uses it; this one is "SNX3" in ASCII.
BUILD_LOCK_KEY = 0x534E5833


class DbtBuildError(Exception):
    """dbt build did not pass. Holds node IDs only, never compiled SQL or row values.

    A plain Exception subclass, not a dataclass: the fields are passed to Exception.__init__ so args
    round-trips through pickle and copy (DbtBuildError(*args)), and the exception stays hashable.
    """

    def __init__(self, returncode: int, failed_nodes: Sequence[str] = (), tests_only: bool = False) -> None:
        super().__init__(returncode, list(failed_nodes), tests_only)
        self.returncode = returncode
        self.failed_nodes = list(failed_nodes)
        # True when only data tests failed. Retrying rebuilds the same data, so it cannot help.
        self.tests_only = tests_only

    def __str__(self) -> str:
        if not self.failed_nodes:
            return f"dbt build exited with code {self.returncode} before reporting results"
        shown = ", ".join(self.failed_nodes[:5])
        more = f" (+{len(self.failed_nodes) - 5} more)" if len(self.failed_nodes) > 5 else ""
        return f"dbt build failed on {len(self.failed_nodes)} node(s): {shown}{more}"


class BuildInProgressError(RuntimeError):
    """Another build or swap holds the build lock. Transient: the task's retry tries again."""


class StaleBuildError(RuntimeError):
    """silver_build is not a build this run produced and passed. Retrying publish cannot change that."""


def reset_build_schema(conn: Connection) -> None:
    """Drop leftovers from an earlier failed build, so nothing stale can be published. Commits."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(BUILD_SCHEMA)))
    conn.commit()


def summarize_run_results(results: list[dict]) -> Counter[str]:
    """Count dbt node results by status ('success', 'pass', 'fail', 'error', 'skipped', ...)."""
    return Counter(str(r.get("status")) for r in results)


def run_dbt_build(project_dir: str, timeout_seconds: int = 1200) -> dict[str, int]:
    """Run `dbt build` into BUILD_SCHEMA and return node counts by status, or raise DbtBuildError.

    target/ and logs/ go to a temporary directory: the project directory is shared with developers,
    and two writers (a manual run and a scheduled one) must not mix their artifacts.
    """
    with tempfile.TemporaryDirectory(prefix="dbt-") as work:
        command = [
            "dbt",
            "build",
            "--project-dir",
            project_dir,
            "--target-path",
            os.path.join(work, "target"),
            "--log-path",
            os.path.join(work, "logs"),
            "--vars",
            json.dumps({"silver_schema": BUILD_SCHEMA}),
            "--no-use-colors",
        ]
        log.info("running %s", " ".join(command))
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds, check=False, env=os.environ.copy()
        )
        # dbt's console output names nodes and statuses, not row values, so it can go to the task log.
        for line in completed.stdout.splitlines():
            log.info("dbt | %s", line)
        if completed.stderr.strip():
            log.warning("dbt stderr | %s", completed.stderr.strip())

        results_file = Path(work, "target", "run_results.json")
        results = json.loads(results_file.read_text())["results"] if results_file.is_file() else []

    counts = summarize_run_results(results)
    if completed.returncode != 0:
        failed = [r["unique_id"] for r in results if r.get("status") in ("fail", "error")]
        errored_models = [r for r in results if r.get("status") == "error"]
        raise DbtBuildError(
            returncode=completed.returncode,
            failed_nodes=failed,
            tests_only=bool(failed) and not errored_models,
        )
    return dict(counts)


def _table_oids(cur, schema: str) -> dict[str, int]:
    """OIDs of the REQUIRED_TABLES present in schema. dbt replaces a table with a new one (new OID)."""
    cur.execute(
        """
        SELECT c.relname, c.oid::bigint
        FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = ANY(%s) AND c.relkind IN ('r', 'p')
        """,
        (schema, list(REQUIRED_TABLES)),
    )
    return dict(cur.fetchall())


def _build_stamp(cur) -> dict | None:
    cur.execute(
        "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = %s", (BUILD_SCHEMA,)
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return None


def stamp_build(conn: Connection, airflow_run_id: str) -> None:
    """Mark silver_build as this run's passing build (see the module docstring). Commits."""
    with conn.cursor() as cur:
        oids = _table_oids(cur, BUILD_SCHEMA)
        missing = set(REQUIRED_TABLES) - oids.keys()
        if missing:
            raise StaleBuildError(f"{BUILD_SCHEMA} is missing {sorted(missing)} after a passing build")
        stamp = json.dumps({"airflow_run_id": airflow_run_id, "tables": oids}, sort_keys=True)
        cur.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(sql.Identifier(BUILD_SCHEMA), sql.Literal(stamp)))
    conn.commit()


def build(conn: Connection, airflow_run_id: str, run_dbt: Callable[[], dict[str, int]]) -> dict[str, int]:
    """Rebuild silver_build from scratch with run_dbt and stamp it if it passed.

    run_dbt is normally `lambda: run_dbt_build(project_dir)`; tests pass a fake. On any failure the
    partial build is dropped before the error propagates, so it can never be published.
    """
    with conn.cursor() as cur:
        # Session-level, so it spans the commits below and the whole dbt run. Released at the end, or
        # by PostgreSQL when the connection drops, so a crashed task cannot leave it held.
        cur.execute("SELECT pg_try_advisory_lock(%s)", (BUILD_LOCK_KEY,))
        acquired = cur.fetchone()[0]
    conn.commit()
    if not acquired:
        raise BuildInProgressError("another silver build or publish is running; retrying later")
    try:
        reset_build_schema(conn)
        try:
            counts = run_dbt()
            stamp_build(conn, airflow_run_id)
        except BaseException:
            try:
                conn.rollback()
                reset_build_schema(conn)
            except psycopg2.Error:
                # Database gone: the next build resets the schema first, and the missing stamp stops any
                # publish of these tables meanwhile. Keep the original error.
                log.warning("could not drop the failed build; it stays unstamped and unpublishable")
            raise
        return counts
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (BUILD_LOCK_KEY,))
            conn.commit()
        except psycopg2.Error:
            pass  # the connection is gone, and its lock went with it


def publish(
    conn: Connection,
    airflow_run_id: str,
    build_counts: dict[str, int],
    attempt: int,
    lock_timeout: str = SWAP_LOCK_TIMEOUT,
) -> dict[str, int]:
    """Swap BUILD_SCHEMA in as LIVE_SCHEMA and mark the silver run succeeded, in one transaction.

    Returns the counts recorded on the run: dbt node counts plus published row counts per table.
    Raises StaleBuildError (and rolls back, leaving the live silver untouched) unless silver_build
    carries this run's stamp and its tables are still the ones stamped.
    If this run already published (a cleared rerun, or a retry after a commit whose task then died),
    returns the recorded counts and swaps nothing: silver_build is not this run's build any more.
    """
    try:
        already = succeeded_counts(conn, SILVER_PUBLISH, airflow_run_id)
        if already is not None:
            conn.rollback()
            log.info("this run already published silver; nothing to do")
            return already
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = %s", (lock_timeout,))
            # Waits for a running build to finish (then its stamp is checked), up to lock_timeout.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (BUILD_LOCK_KEY,))
            stamp = _build_stamp(cur)
            if stamp is None or stamp.get("airflow_run_id") != airflow_run_id:
                raise StaleBuildError(f"{BUILD_SCHEMA} is not this run's passing build; rerun build_silver")
            if stamp.get("tables") != _table_oids(cur, BUILD_SCHEMA):
                raise StaleBuildError(f"{BUILD_SCHEMA} changed after this run's build passed; rerun build_silver")

            counts = {f"dbt_{status}": n for status, n in build_counts.items()}
            for table in REQUIRED_TABLES:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(BUILD_SCHEMA), sql.Identifier(table))
                )
                counts[f"{table}_rows"] = cur.fetchone()[0]

            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(PREVIOUS_SCHEMA)))
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (LIVE_SCHEMA,))
            if cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(
                        sql.Identifier(LIVE_SCHEMA), sql.Identifier(PREVIOUS_SCHEMA)
                    )
                )
            cur.execute(
                sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(sql.Identifier(BUILD_SCHEMA), sql.Identifier(LIVE_SCHEMA))
            )
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(PREVIOUS_SCHEMA)))
            # Sets 'succeeded' from whatever state an earlier publish try left ('retrying' included).
            mark_succeeded(conn, SILVER_PUBLISH, airflow_run_id, counts, attempt)
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except psycopg2.Error:
            # The connection is already gone (e.g. the database restarted mid-swap). The server has
            # rolled the transaction back anyway; re-raise the original error, not the rollback's.
            log.warning("rollback after a failed publish also failed; the connection is closed")
        raise
    log.info("published silver: %s", counts)
    return counts
