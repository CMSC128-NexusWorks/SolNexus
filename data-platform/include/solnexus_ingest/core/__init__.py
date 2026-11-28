"""Plumbing every SolNexus pipeline shares, whatever the source.

orchestration: Airflow names the DAGs share (warehouse connection, datasets, schedule timezone).
runs: run status in app.pipeline_runs, the summary the dashboard reads.
"""
