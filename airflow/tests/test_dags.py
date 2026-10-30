"""DAG integrity: every DAG file imports cleanly and ingest_email keeps its safety settings."""

from pathlib import Path

import pytest
from airflow.models import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_dags_import_without_errors(dagbag):
    assert dagbag.import_errors == {}


def test_ingest_email_runs_one_at_a_time_and_is_not_scheduled_yet(dagbag):
    dag = dagbag.dags["ingest_email"]  # parsed DAG; get_dag() would need the metadata DB

    assert dag.max_active_runs == 1  # overlapping runs would race on the checkpoint
    assert dag.schedule_interval is None  # scheduling belongs to SNX-33
    assert [t.task_id for t in dag.tasks] == ["sync_gmail"]
