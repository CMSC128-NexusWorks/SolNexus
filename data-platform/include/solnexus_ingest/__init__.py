"""Airflow-side helpers for the SolNexus pipelines: run status, shared DAG names, silver publication.

Source connectors live outside Airflow, in their own services (data-ingestion/google-workspace/). This package is
plain Python so it can be unit-tested without running Airflow; the DAGs in data-platform/dags wire it up.
"""
