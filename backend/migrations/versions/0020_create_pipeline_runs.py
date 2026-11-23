"""Create app.pipeline_runs and the app.pipeline_status view.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-30
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per Airflow DAG run of a pipeline, written by the DAGs' tasks and callbacks (SNX-33).
    # The row is updated in place across task retries, so its status is the run's current state.
    # 'silver_publish' becomes 'succeeded' only in the same transaction that swaps the freshly built
    # silver schema in, so a failed dbt build can never make old data look fresh. Its finished_at is the
    # swap time. data_as_of is the time the build started reading bronze and app, recorded before dbt
    # ran: every change committed before it is in that silver. It is the contract's published_at, so the
    # API's read-through rule (show app rows newer than published_at with pending_projection) never
    # treats a row the build missed as published.
    # counts holds per-run numbers only; error_summary holds an exception class and its first line,
    # never message content, addresses or tokens.
    op.execute(
        """
        CREATE TABLE app.pipeline_runs (
            pipeline_run_id uuid        NOT NULL DEFAULT gen_random_uuid(),
            pipeline        text        NOT NULL,
            dag_id          text        NOT NULL,
            airflow_run_id  text        NOT NULL,
            status          text        NOT NULL,
            attempt         integer     NOT NULL DEFAULT 1,
            started_at      timestamptz NOT NULL DEFAULT now(),
            finished_at     timestamptz,
            counts          jsonb       NOT NULL DEFAULT '{}'::jsonb,
            error_summary   text,
            data_as_of      timestamptz,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pipeline_runs_pkey PRIMARY KEY (pipeline_run_id),
            CONSTRAINT pipeline_runs_airflow_run_key UNIQUE (pipeline, airflow_run_id),
            CONSTRAINT pipeline_runs_pipeline_check CHECK (pipeline IN ('gmail_ingest', 'silver_publish')),
            CONSTRAINT pipeline_runs_status_check CHECK (status IN ('running', 'retrying', 'succeeded', 'failed')),
            CONSTRAINT pipeline_runs_attempt_check CHECK (attempt >= 1),
            -- A finished run has an end time; a running or retrying one does not.
            CONSTRAINT pipeline_runs_finished_check CHECK (
                (status IN ('succeeded', 'failed')) = (finished_at IS NOT NULL)
            ),
            CONSTRAINT pipeline_runs_counts_check CHECK (jsonb_typeof(counts) = 'object'),
            -- Only a silver publication has a data snapshot time, and a succeeded one always has it.
            CONSTRAINT pipeline_runs_data_as_of_check CHECK (
                CASE WHEN pipeline = 'silver_publish' AND status = 'succeeded' THEN data_as_of IS NOT NULL
                     WHEN pipeline <> 'silver_publish' THEN data_as_of IS NULL
                     ELSE true END
            )
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER pipeline_runs_touch_updated_at
            BEFORE UPDATE ON app.pipeline_runs
            FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    # The status view reads the latest run and the latest success per pipeline.
    op.execute("CREATE INDEX pipeline_runs_latest_idx ON app.pipeline_runs (pipeline, started_at DESC)")
    op.execute(
        "CREATE INDEX pipeline_runs_last_success_idx ON app.pipeline_runs (pipeline, finished_at DESC) "
        "WHERE status = 'succeeded'"
    )
    op.execute(
        "COMMENT ON TABLE app.pipeline_runs IS "
        "'One row per Airflow run. silver_publish succeeded rows mark silver publications.'"
    )

    # One row per known pipeline, even before its first run, so the API can report "never run"
    # rather than no row. last_succeeded_data_as_of of 'silver_publish' is the contract's published_at.
    op.execute(
        """
        CREATE VIEW app.pipeline_status AS
        SELECT
            p.pipeline,
            latest.status        AS last_run_status,
            latest.started_at    AS last_run_started_at,
            latest.finished_at   AS last_run_finished_at,
            latest.error_summary AS last_run_error_summary,
            ok.finished_at       AS last_succeeded_at,
            ok.data_as_of        AS last_succeeded_data_as_of,
            ok.counts            AS last_succeeded_counts
        FROM (VALUES ('gmail_ingest'), ('silver_publish')) AS p (pipeline)
        LEFT JOIN LATERAL (
            SELECT r.status, r.started_at, r.finished_at, r.error_summary
            FROM app.pipeline_runs AS r
            WHERE r.pipeline = p.pipeline
            ORDER BY r.started_at DESC
            LIMIT 1
        ) AS latest ON true
        LEFT JOIN LATERAL (
            SELECT r.finished_at, r.data_as_of, r.counts
            FROM app.pipeline_runs AS r
            WHERE r.pipeline = p.pipeline AND r.status = 'succeeded'
            ORDER BY r.finished_at DESC
            LIMIT 1
        ) AS ok ON true
        """
    )
    op.execute(
        "COMMENT ON VIEW app.pipeline_status IS "
        "'Latest run and last success per pipeline; silver_publish last_succeeded_data_as_of is published_at.'"
    )


def downgrade() -> None:
    op.execute("DROP VIEW app.pipeline_status")
    op.execute("DROP TABLE app.pipeline_runs")
