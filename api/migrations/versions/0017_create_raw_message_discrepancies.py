"""Create bronze.raw_message_discrepancies.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-29
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A replayed message whose source key already exists in bronze.raw_messages but whose payload bytes
    # differ. The first copy stays the evidence of record; the differing copy is kept here for review
    # (phase1-data-api-v1 "Message envelope and replay").
    op.execute(
        """
        CREATE TABLE bronze.raw_message_discrepancies (
            discrepancy_id          uuid        NOT NULL DEFAULT gen_random_uuid(),
            raw_message_id          uuid        NOT NULL,
            received_payload_bytes  bytea       NOT NULL,
            received_payload_sha256 bytea       GENERATED ALWAYS AS (sha256(received_payload_bytes)) STORED,
            job_run_id              text        NULL,
            detected_at             timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT raw_message_discrepancies_pkey PRIMARY KEY (discrepancy_id),
            CONSTRAINT raw_message_discrepancies_raw_message_id_fkey
                FOREIGN KEY (raw_message_id) REFERENCES bronze.raw_messages (raw_message_id),
            -- Re-fetching the same differing copy on every run must not pile up identical rows.
            CONSTRAINT raw_message_discrepancies_payload_key UNIQUE (raw_message_id, received_payload_sha256)
        )
        """
    )
    # Evidence, like bronze.raw_messages: no edits or deletes.
    op.execute(
        """
        CREATE TRIGGER raw_message_discrepancies_append_only
            BEFORE UPDATE OR DELETE ON bronze.raw_message_discrepancies
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER raw_message_discrepancies_no_truncate
            BEFORE TRUNCATE ON bronze.raw_message_discrepancies
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        "COMMENT ON TABLE bronze.raw_message_discrepancies IS "
        "'Replays whose payload differs from the stored first copy. Append-only; for staff/dev review.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE bronze.raw_message_discrepancies")
