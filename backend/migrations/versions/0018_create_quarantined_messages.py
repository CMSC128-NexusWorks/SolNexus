"""Create bronze.quarantined_messages.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-30
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A source message the connector could not parse or that PostgreSQL rejected. Recording it here
    # lets the run continue and its checkpoint advance: without this, one malformed message would fail
    # every run forever, because the cursor only moves after the whole page is stored.
    op.execute(
        """
        CREATE TABLE bronze.quarantined_messages (
            quarantine_id     uuid        NOT NULL DEFAULT gen_random_uuid(),
            source_channel    text        NOT NULL,
            source_account_id text        NOT NULL,
            source_message_id text        NOT NULL,
            -- "<stage>:<exception class>", e.g. parse_error:HeaderParseError. Never message content.
            reason            text        NOT NULL,
            -- The source bytes when they could be read, kept as evidence for fixing the parser.
            payload_bytes     bytea       NULL,
            job_run_id        text        NULL,
            quarantined_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT quarantined_messages_pkey PRIMARY KEY (quarantine_id),
            -- A resync meets the same bad message again; keep the first record only.
            CONSTRAINT quarantined_messages_source_key UNIQUE (source_channel, source_account_id, source_message_id),
            CONSTRAINT quarantined_messages_source_channel_check CHECK (source_channel IN ('gmail')),
            CONSTRAINT quarantined_messages_reason_check CHECK (btrim(reason) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER quarantined_messages_append_only
            BEFORE UPDATE OR DELETE ON bronze.quarantined_messages
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER quarantined_messages_no_truncate
            BEFORE TRUNCATE ON bronze.quarantined_messages
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        "COMMENT ON TABLE bronze.quarantined_messages IS "
        "'Messages a connector could not parse or store. Append-only; a later successful ingest still lands in raw_messages.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE bronze.quarantined_messages")
