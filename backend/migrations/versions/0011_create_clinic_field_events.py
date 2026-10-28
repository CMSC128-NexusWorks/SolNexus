"""Create app.lead_field_name and app.clinic_field_events.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-28
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Operational fields staff may edit or that an import may initialize. Shared by field audit and
    # import field reviews so both reject an unknown field name the same way.
    op.execute(
        """
        CREATE DOMAIN app.lead_field_name AS text CHECK (
            VALUE IN (
                'clinic_name', 'contact_person', 'person_spoken_to', 'calling_notes', 'contact_number',
                'email', 'region', 'province', 'municipality', 'address', 'status_code',
                'next_action_date', 'next_step', 'point_person', 'discovery_source'
            )
        )
        """
    )
    # Append-only audit of row edits and clinic-name confirmation (FR-21). Values are jsonb so any field
    # type fits; JSON null is an explicit clear, which stays distinct from a missing value.
    op.execute(
        """
        CREATE TABLE app.clinic_field_events (
            event_id             uuid               NOT NULL DEFAULT gen_random_uuid(),
            clinic_id            uuid               NULL,
            inquiry_id           uuid               NULL,
            field_name           app.lead_field_name NOT NULL,
            old_value            jsonb              NOT NULL,
            new_value            jsonb              NOT NULL,
            changed_by           uuid               NOT NULL,
            changed_at           timestamptz        NOT NULL DEFAULT now(),
            reason               text               NULL,
            -- Supporting bronze messages, e.g. the question and reply behind a name confirmation.
            evidence_message_ids uuid[]             NULL,
            CONSTRAINT clinic_field_events_pkey PRIMARY KEY (event_id),
            CONSTRAINT clinic_field_events_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT clinic_field_events_inquiry_id_fkey
                FOREIGN KEY (inquiry_id) REFERENCES app.lead_inquiries (inquiry_id),
            CONSTRAINT clinic_field_events_changed_by_fkey
                FOREIGN KEY (changed_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT clinic_field_events_target_check CHECK (num_nonnulls(clinic_id, inquiry_id) = 1),
            CONSTRAINT clinic_field_events_changed_check CHECK (old_value IS DISTINCT FROM new_value),
            -- Correcting an already confirmed clinic name needs an audit reason.
            CONSTRAINT clinic_field_events_name_reason_check CHECK (
                NOT (clinic_id IS NOT NULL AND field_name = 'clinic_name' AND old_value <> 'null'::jsonb)
                OR coalesce(btrim(reason), '') <> ''  -- coalesce: a CHECK passes on NULL
            )
        )
        """
    )
    op.execute("CREATE INDEX clinic_field_events_clinic_idx ON app.clinic_field_events (clinic_id, changed_at)")
    op.execute("CREATE INDEX clinic_field_events_inquiry_idx ON app.clinic_field_events (inquiry_id, changed_at)")
    op.execute(
        """
        CREATE TRIGGER clinic_field_events_append_only
            BEFORE UPDATE OR DELETE ON app.clinic_field_events
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_field_events_no_truncate
            BEFORE TRUNCATE ON app.clinic_field_events
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.clinic_field_events")
    op.execute("DROP DOMAIN app.lead_field_name")
