"""DAG integrity: every DAG file imports cleanly and keeps its schedule and safety settings."""

from pathlib import Path

import pytest
from airflow.models import DagBag
from airflow.timetables.datasets import DatasetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from solnexus_ingest.orchestration import GMAIL_BRONZE

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_dags_import_without_errors(dagbag):
    assert dagbag.import_errors == {}
    assert set(dagbag.dag_ids) == {"ingest_email", "transform_bronze_to_silver"}


def test_ingest_email_runs_hourly_one_at_a_time(dagbag):
    dag = dagbag.dags["ingest_email"]  # parsed DAG; get_dag() would need the metadata DB

    assert dag.max_active_runs == 1  # overlapping runs would race on the checkpoint
    assert not dag.catchup
    assert isinstance(dag.timetable, CronTriggerTimetable)
    assert dag.timetable.summary == "0 * * * *"
    assert [t.task_id for t in dag.tasks] == ["sync_gmail"]


def test_ingest_email_triggers_silver_and_records_failures(dagbag):
    task = dagbag.dags["ingest_email"].get_task("sync_gmail")

    assert task.outlets == [GMAIL_BRONZE]
    assert task.on_retry_callback and task.on_failure_callback
    assert task.retries == 2


def test_silver_runs_after_ingestion_and_hourly_as_a_fallback(dagbag):
    dag = dagbag.dags["transform_bronze_to_silver"]

    assert isinstance(dag.timetable, DatasetOrTimeSchedule)
    assert [uri for uri, _ in dag.timetable.dataset_condition.iter_datasets()] == [GMAIL_BRONZE.uri]
    assert dag.max_active_runs == 1  # runs share the silver_build staging schema


def test_silver_publishes_only_after_the_build(dagbag):
    dag = dagbag.dags["transform_bronze_to_silver"]
    build, publish = dag.get_task("build_silver"), dag.get_task("publish_silver")

    assert publish.upstream_task_ids == {"build_silver"}
    for task in (build, publish):
        assert task.on_retry_callback and task.on_failure_callback
        assert task.retries == 2
