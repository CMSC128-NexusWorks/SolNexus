"""Google Workspace master: everything that talks to Google and writes what it read to bronze.

Plain Python with no Airflow imports, so it can run inside the master service, inside an Airflow task
during the transition (data-ingestion/google-workspace/README.md), and in unit tests.
"""
