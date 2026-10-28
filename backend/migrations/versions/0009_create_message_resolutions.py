"""Create app.message_resolutions.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-28
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
        """
    )
    # Current association decision per raw message, kept outside bronze so evidence stays untouched.
    # Reason codes come from the identity contract.
    op.execute(
        """
        CREATE TABLE app.message_resolutions (
            raw_message_id    uuid        NOT NULL,
            clinic_id         uuid        NULL,
            resolution_status text        NOT NULL,
            review_reason     text        NULL,
            resolved_by       uuid        NULL,
            resolved_at       timestamptz NULL,
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT message_resolutions_pkey PRIMARY KEY (raw_message_id),
            CONSTRAINT message_resolutions_raw_message_id_fkey
                FOREIGN KEY (raw_message_id) REFERENCES bronze.raw_messages (raw_message_id),
            CONSTRAINT message_resolutions_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT message_resolutions_resolved_by_fkey
                FOREIGN KEY (resolved_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT message_resolutions_status_check CHECK (resolution_status IN ('linked', 'needs_review')),
            CONSTRAINT message_resolutions_review_reason_check CHECK (
                review_reason IN (
                    'no_match', 'multiple_candidates', 'unconfirmed_source_identity',
                    'incomplete_source_identity', 'multiple_confirmed_mappings', 'conflicting_evidence'
                )
            ),
            -- linked: a clinic and no reason. needs_review: no clinic and a reason.
            CONSTRAINT message_resolutions_outcome_check CHECK (
                (resolution_status = 'linked' AND clinic_id IS NOT NULL AND review_reason IS NULL)
                OR (resolution_status = 'needs_review' AND clinic_id IS NULL AND review_reason IS NOT NULL)
            ),
            -- resolved_by/resolved_at mark a staff decision; system decisions leave both NULL.
            CONSTRAINT message_resolutions_resolved_check CHECK ((resolved_by IS NULL) = (resolved_at IS NULL))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX message_resolutions_clinic_id_idx ON app.message_resolutions (clinic_id)
            WHERE resolution_status = 'linked'
        """
    )
    op.execute(
        """
        CREATE INDEX message_resolutions_review_idx ON app.message_resolutions (review_reason)
            WHERE resolution_status = 'needs_review'
        """
    )
    op.execute(
        """
        CREATE TRIGGER message_resolutions_touch_updated_at
            BEFORE UPDATE ON app.message_resolutions
            FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    op.execute(
        "COMMENT ON TABLE app.message_resolutions IS "
        "'Current linked/needs_review decision per raw message. Every change also writes message_resolution_events.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.message_resolutions")
    op.execute("DROP FUNCTION app.touch_updated_at()")
