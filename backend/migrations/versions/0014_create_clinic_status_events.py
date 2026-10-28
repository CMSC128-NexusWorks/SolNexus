"""Create app.clinic_status_events.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Append-only status evidence for funnel metrics (FR-15). Staff events are confirmed transitions with
    # an actor. An imported status is a baseline observation tied to its import row: it says what the
    # workbook showed, not when the clinic entered that stage. Parser suggestions never write here.
    op.execute(
        """
        CREATE TABLE app.clinic_status_events (
            event_id        uuid        NOT NULL DEFAULT gen_random_uuid(),
            clinic_id       uuid        NOT NULL,
            old_status_code text        NULL,
            new_status_code text        NULL,
            origin          text        NOT NULL,
            recorded_at     timestamptz NOT NULL DEFAULT now(),
            changed_by      uuid        NULL,
            import_row_id   uuid        NULL,
            reason          text        NULL,
            CONSTRAINT clinic_status_events_pkey PRIMARY KEY (event_id),
            CONSTRAINT clinic_status_events_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT clinic_status_events_changed_by_fkey
                FOREIGN KEY (changed_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT clinic_status_events_import_row_id_fkey
                FOREIGN KEY (import_row_id) REFERENCES app.import_rows (import_row_id),
            -- One baseline per import row, so a retried import cannot record it twice.
            CONSTRAINT clinic_status_events_import_row_id_key UNIQUE (import_row_id),
            CONSTRAINT clinic_status_events_status_check CHECK (
                old_status_code IN ('contacted', 'proposal_sent', 'awaiting_demo', 'follow_up_needed', 'closed')
                AND new_status_code IN ('contacted', 'proposal_sent', 'awaiting_demo', 'follow_up_needed', 'closed')
            ),
            CONSTRAINT clinic_status_events_origin_check CHECK (
                origin IN ('manual_create', 'inquiry_confirmation', 'row_edit', 'import_baseline')
            ),
            CONSTRAINT clinic_status_events_actor_check CHECK (
                CASE WHEN origin = 'import_baseline'
                    THEN import_row_id IS NOT NULL AND changed_by IS NULL
                         AND old_status_code IS NULL AND new_status_code IS NOT NULL
                    ELSE changed_by IS NOT NULL AND import_row_id IS NULL
                         AND old_status_code IS DISTINCT FROM new_status_code
                END
            )
        )
        """
    )
    op.execute("CREATE INDEX clinic_status_events_clinic_idx ON app.clinic_status_events (clinic_id, recorded_at)")
    op.execute(
        """
        CREATE TRIGGER clinic_status_events_append_only
            BEFORE UPDATE OR DELETE ON app.clinic_status_events
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_status_events_no_truncate
            BEFORE TRUNCATE ON app.clinic_status_events
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.clinic_status_events")
