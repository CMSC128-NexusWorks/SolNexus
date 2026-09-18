from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="ingest_email",
    description="Placeholder DAG for Gmail ingestion (Phase 1).",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["phase1", "ingestion"],
)
def ingest_email():

    @task
    def placeholder():
        pass

    placeholder()


ingest_email()