from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="transform_bronze_to_silver",
    description="Placeholder DAG for dbt bronze-to-silver runs (Phase 1).",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["phase1", "transform"],
)
def transform_bronze_to_silver():

    @task
    def placeholder():
        pass

    placeholder()


transform_bronze_to_silver()