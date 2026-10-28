"""Create app.lead_inquiries.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A first contact whose clinic is not yet known. There is deliberately no clinic_name column:
    # the name exists only on app.clinics after staff confirm it, so a guessed name cannot be stored here.
    op.execute(
        """
        CREATE TABLE app.lead_inquiries (
            inquiry_id              uuid        NOT NULL DEFAULT gen_random_uuid(),
            source_channel          text        NOT NULL,
            source_account_id       text        NOT NULL,
            external_participant_id text        NULL,
            origin_raw_message_id   uuid        NOT NULL,
            clinic_name_state       text        NOT NULL DEFAULT 'unknown',
            contact_person          text        NULL,
            contact_number          text        NULL,
            email                   text        NULL,
            status_code             text        NULL,
            next_action_date        date        NULL,
            next_step               text        NULL,
            calling_notes           text        NULL,
            state                   text        NOT NULL DEFAULT 'open',
            version                 integer     NOT NULL DEFAULT 1,
            created_at              timestamptz NOT NULL DEFAULT now(),
            updated_at              timestamptz NOT NULL DEFAULT now(),
            closed_at               timestamptz NULL,
            confirmed_clinic_id     uuid        NULL,
            CONSTRAINT lead_inquiries_pkey PRIMARY KEY (inquiry_id),
            -- The message that opened the inquiry; also its key when the source identity is incomplete.
            CONSTRAINT lead_inquiries_origin_raw_message_id_key UNIQUE (origin_raw_message_id),
            CONSTRAINT lead_inquiries_origin_raw_message_id_fkey
                FOREIGN KEY (origin_raw_message_id) REFERENCES bronze.raw_messages (raw_message_id),
            CONSTRAINT lead_inquiries_confirmed_clinic_id_fkey
                FOREIGN KEY (confirmed_clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT lead_inquiries_source_channel_check CHECK (source_channel IN ('gmail')),
            CONSTRAINT lead_inquiries_source_account_id_check CHECK (btrim(source_account_id) <> ''),
            CONSTRAINT lead_inquiries_participant_check CHECK (btrim(external_participant_id) <> ''),
            CONSTRAINT lead_inquiries_state_check CHECK (state IN ('open', 'closed')),
            CONSTRAINT lead_inquiries_closed_at_check CHECK ((state = 'closed') = (closed_at IS NOT NULL)),
            CONSTRAINT lead_inquiries_clinic_name_state_check CHECK (clinic_name_state IN ('unknown', 'confirmed')),
            -- Confirmed means staff linked a clinic, which also closes the inquiry.
            CONSTRAINT lead_inquiries_confirmation_check CHECK (
                (clinic_name_state = 'confirmed') = (confirmed_clinic_id IS NOT NULL)
                AND (clinic_name_state = 'unknown' OR state = 'closed')
            ),
            CONSTRAINT lead_inquiries_status_code_check CHECK (
                status_code IN ('contacted', 'proposal_sent', 'awaiting_demo', 'follow_up_needed', 'closed')
            ),
            CONSTRAINT lead_inquiries_version_check CHECK (version >= 1)
        )
        """
    )
    # One open inquiry per complete source identity. Incomplete keys (NULL participant) stay separate
    # rows keyed by their origin message and are never merged on a guess.
    op.execute(
        """
        CREATE UNIQUE INDEX lead_inquiries_open_source_identity_key ON app.lead_inquiries
            (source_channel, source_account_id, external_participant_id)
            WHERE state = 'open' AND external_participant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX lead_inquiries_confirmed_clinic_id_idx ON app.lead_inquiries (confirmed_clinic_id)"
    )
    op.execute("CREATE INDEX lead_inquiries_next_action_date_idx ON app.lead_inquiries (next_action_date)")
    op.execute(
        """
        CREATE TRIGGER lead_inquiries_bump_row_version
            BEFORE UPDATE ON app.lead_inquiries
            FOR EACH ROW EXECUTE FUNCTION app.bump_row_version()
        """
    )
    op.execute(
        "COMMENT ON TABLE app.lead_inquiries IS "
        "'Unknown-name first contacts. Kept after closure for audit; never creates or links a clinic by itself.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.lead_inquiries")
