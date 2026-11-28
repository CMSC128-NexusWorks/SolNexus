"""Create bronze.raw_messages.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE bronze.raw_messages (
            raw_message_id          uuid        NOT NULL DEFAULT gen_random_uuid(),
            source_channel          text        NOT NULL,
            source_account_id       text        NOT NULL,
            source_message_id       text        NOT NULL,
            source_thread_id        text        NULL,
            external_participant_id text        NULL,
            direction               text        NOT NULL,
            source_sender_id        text        NULL,
            source_recipient_ids    jsonb       NOT NULL DEFAULT '[]'::jsonb,
            source_event_at         timestamptz NULL,
            ingested_at             timestamptz NOT NULL DEFAULT now(),
            raw_payload_bytes       bytea       NOT NULL,
            raw_payload_sha256      bytea       GENERATED ALWAYS AS (sha256(raw_payload_bytes)) STORED,
            parsed_payload          jsonb       NULL,
            CONSTRAINT raw_messages_pkey PRIMARY KEY (raw_message_id),
            -- Replay protection. Message IDs are unique only within one mailbox or Page, so the key is scoped.
            CONSTRAINT raw_messages_source_key UNIQUE (source_channel, source_account_id, source_message_id),
            -- Phase 2 widens this list for facebook and viber in a new revision.
            CONSTRAINT raw_messages_source_channel_check CHECK (source_channel IN ('gmail')),
            CONSTRAINT raw_messages_direction_check CHECK (direction IN ('inbound', 'outbound')),
            -- A blank ID would make every unidentifiable message collide on one key; connectors quarantine those.
            CONSTRAINT raw_messages_source_ids_check CHECK (
                btrim(source_account_id) <> '' AND btrim(source_message_id) <> ''
            ),
            -- Blank means unknown: store NULL so resolution reports incomplete_source_identity.
            CONSTRAINT raw_messages_participant_check CHECK (btrim(external_participant_id) <> ''),
            CONSTRAINT raw_messages_recipient_ids_check CHECK (jsonb_typeof(source_recipient_ids) = 'array')
        )
        """
    )

    # Re-evaluation after a mapping change scans one exact source identity key, in event order.
    op.execute(
        """
        CREATE INDEX raw_messages_source_identity_idx ON bronze.raw_messages
            (source_channel, source_account_id, external_participant_id, source_event_at)
        """
    )
    # Conversation view: one thread within one connected account.
    op.execute(
        """
        CREATE INDEX raw_messages_thread_idx ON bronze.raw_messages
            (source_channel, source_account_id, source_thread_id, source_event_at)
            WHERE source_thread_id IS NOT NULL
        """
    )
    # Incremental dbt and connector catch-up read by arrival time, not by source time.
    op.execute("CREATE INDEX raw_messages_ingested_at_idx ON bronze.raw_messages (ingested_at)")

    op.execute(
        """
        CREATE TRIGGER raw_messages_append_only
            BEFORE UPDATE OR DELETE ON bronze.raw_messages
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    # Row-level triggers do not fire on TRUNCATE.
    op.execute(
        """
        CREATE TRIGGER raw_messages_no_truncate
            BEFORE TRUNCATE ON bronze.raw_messages
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )

    op.execute(
        "COMMENT ON TABLE bronze.raw_messages IS "
        "'One row per source message, append-only. First payload wins; dbt and resolution never rewrite it.'"
    )
    op.execute(
        "COMMENT ON COLUMN bronze.raw_messages.raw_payload_bytes IS "
        "'Exact bytes returned by the source API. Evidence of record; parsed_payload is only a query aid.'"
    )
    op.execute(
        "COMMENT ON COLUMN bronze.raw_messages.raw_payload_sha256 IS "
        "'Lets a connector detect a replay whose payload differs from the stored first copy.'"
    )
    op.execute(
        "COMMENT ON COLUMN bronze.raw_messages.external_participant_id IS "
        "'Clinic-side participant: sender when inbound, recipient when outbound. NULL when not unique.'"
    )


def downgrade() -> None:
    # DROP TABLE is not a row operation, so the append-only triggers do not block it.
    op.execute("DROP TABLE bronze.raw_messages")
