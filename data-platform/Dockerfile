FROM apache/airflow:2.10.5-python3.12

USER airflow
# dbt-core is pinned separately because dbt-postgres does not bound it tightly. The dbt project
# uses unit tests (>=1.8) and the generic-test "arguments:" block (>=1.10); 1.12 is the version
# it is tested on. dbt_project.yml repeats this bound as require-dbt-version.
RUN pip install --no-cache-dir "dbt-core>=1.12,<2.0" "dbt-postgres>=1.8,<2.0"
