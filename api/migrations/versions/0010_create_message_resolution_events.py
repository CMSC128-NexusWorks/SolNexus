"""Create app.message_resolution_events.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-28
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Append-only history of changed resolutions. The writer updates message_resolutions and inserts the
    # event in one transaction, so a retried re-evaluation batch finds nothing changed and inserts nothing.
    op.execute(
        """
        CREATE TABLE app.message_resolution_events (
            event_id       uuid        NOT NULL DEFAULT gen_random_uuid(),
            raw_message_id uuid        NOT NULL,
            mapping_id     uuid        NULL,
            old_clinic_id  uuid        NULL,
            new_clinic_id  uuid        NULL,
            old_status     text        NULL,
            new_status     text        NOT NULL,
            reason         text        NOT NULL,
            changed_by     uuid        NULL,
            job_run_id     text        NULL,
            changed_at     timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT message_resolution_events_pkey PRIMARY KEY (event_id),
            CONSTRAINT message_resolution_events_raw_message_id_fkey
                FOREIGN KEY (raw_message_id) REFERENCES app.message_resolutions (raw_message_id),
            -- The confirmation, correction or revocation that triggered a re-evaluation, if any.
            CONSTRAINT message_resolution_events_mapping_id_fkey
                FOREIGN KEY (mapping_id) REFERENCES app.clinic_source_identities (mapping_id),
            CONSTRAINT message_resolution_events_old_clinic_id_fkey
                FOREIGN KEY (old_clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT message_resolution_events_new_clinic_id_fkey
                FOREIGN KEY (new_clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT message_resolution_events_changed_by_fkey
                FOREIGN KEY (changed_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT message_resolution_events_status_check CHECK (
                old_status IN ('linked', 'needs_review') AND new_status IN ('linked', 'needs_review')
            ),
            CONSTRAINT message_resolution_events_reason_check CHECK (btrim(reason) <> ''),
            -- Exactly one actor: a staff user or a system job run.
            CONSTRAINT message_resolution_events_actor_check CHECK (num_nonnulls(changed_by, job_run_id) = 1),
            -- Unchanged resolutions get no event, so retries cannot add duplicates.
            CONSTRAINT message_resolution_events_changed_check CHECK (
                (old_status, old_clinic_id) IS DISTINCT FROM (new_status, new_clinic_id)
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX message_resolution_events_raw_message_idx ON app.message_resolution_events
            (raw_message_id, changed_at)
        """
    )
    op.execute(
        """
        CREATE TRIGGER message_resolution_events_append_only
            BEFORE UPDATE OR DELETE ON app.message_resolution_events
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER message_resolution_events_no_truncate
            BEFORE TRUNCATE ON app.message_resolution_events
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.message_resolution_events")
