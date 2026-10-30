"""Build silver with dbt in a staging schema and publish it atomically (SNX-33).

Why a staging schema: `dbt build` replaces each model and then tests it. Run against silver directly,
a failing test on silver.interactions would leave the new, bad table live, and dbt would skip
silver.leads, so the two would no longer match. Instead dbt builds everything into silver_build, and
publish() swaps that schema in only after the whole build passed. The swap and the 'succeeded' run row
commit in one transaction. So a failed build or swap leaves the previous silver, and the previous
published_at, exactly as they were (data/API contract: "a failed run must not claim a fresh
publication").

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
from collections.abc import Sequence
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as Connection

from solnexus_ingest.runs import SILVER_PUBLISH, mark_succeeded

log = logging.getLogger(__name__)

LIVE_SCHEMA = "silver"
BUILD_SCHEMA = "silver_build"
PREVIOUS_SCHEMA = "silver_previous"
# Published relations the API reads. A build missing one of them is never swapped in.
REQUIRED_TABLES = ("interactions", "leads")
# Long enough for in-flight API reads to finish, short enough that a stuck reader fails the task
# (which Airflow retries) instead of hanging it.
SWAP_LOCK_TIMEOUT = "30s"


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


def _schema_tables(cur, schema: str) -> set[str]:
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,))
    return {name for (name,) in cur.fetchall()}


def publish(conn: Connection, airflow_run_id: str, build_counts: dict[str, int]) -> dict[str, int]:
    """Swap BUILD_SCHEMA in as LIVE_SCHEMA and mark the silver run succeeded, in one transaction.

    Returns the counts recorded on the run: dbt node counts plus published row counts per table.
    Raises (and rolls back, leaving the live silver untouched) if the build schema is incomplete.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = %s", (SWAP_LOCK_TIMEOUT,))
            missing = set(REQUIRED_TABLES) - _schema_tables(cur, BUILD_SCHEMA)
            if missing:
                raise RuntimeError(f"{BUILD_SCHEMA} is missing {sorted(missing)}; not publishing")

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
            mark_succeeded(conn, SILVER_PUBLISH, airflow_run_id, counts)
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
