"""SolNexus source connectors: fetch conversations and store them in bronze.

The package is plain Python so it can be unit-tested without Airflow; the DAGs in airflow/dags only
wire it to Airflow connections and scheduling.
"""
