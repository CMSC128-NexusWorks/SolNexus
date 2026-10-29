"""Create app.ingestion_checkpoints.

Revision ID: 0016
Revises: 0014
Create Date: 2026-10-29

Numbered 0016 because SNX-27's open PR adds 0015. Whichever of the two merges second must set its
down_revision to the other so Alembic keeps a single head.
"""

from alembic import op

revision = "0016"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One incremental-sync cursor per connected account (for Gmail, the mailbox's historyId).
    # The connector updates it in the same transaction as the last message page it stores, so the
    # cursor can never point past a message that is not durable in bronze.
    op.execute(
        """
        CREATE TABLE app.ingestion_checkpoints (
            source_channel    text        NOT NULL,
            source_account_id text        NOT NULL,
            cursor_value      text        NOT NULL,
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ingestion_checkpoints_pkey PRIMARY KEY (source_channel, source_account_id),
            CONSTRAINT ingestion_checkpoints_source_channel_check CHECK (source_channel IN ('gmail')),
            CONSTRAINT ingestion_checkpoints_values_check CHECK (
                btrim(source_account_id) <> '' AND btrim(cursor_value) <> ''
            )
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER ingestion_checkpoints_touch_updated_at
            BEFORE UPDATE ON app.ingestion_checkpoints
            FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    op.execute(
        "COMMENT ON TABLE app.ingestion_checkpoints IS "
        "'Connector resume point per account. Advanced only after the pages it covers are committed.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.ingestion_checkpoints")
