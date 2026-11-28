"""Create app.clinics.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Durable confirmed leads from manual creation, accepted import or a confirmed inquiry.
    # No unique key on name, phone or email: those are candidate evidence, not identity.
    op.execute(
        """
        CREATE TABLE app.clinics (
            clinic_id         uuid        NOT NULL DEFAULT gen_random_uuid(),
            clinic_name       text        NOT NULL,
            contact_person    text        NULL,
            person_spoken_to  text        NULL,
            calling_notes     text        NULL,
            contact_number    text        NULL,
            email             text        NULL,
            region            text        NULL,
            province          text        NULL,
            municipality      text        NULL,
            address           text        NULL,
            status_code       text        NULL,
            next_action_date  date        NULL,
            next_step         text        NULL,
            point_person      text        NULL,
            discovery_source  text        NULL,
            origin            text        NOT NULL,
            version           integer     NOT NULL DEFAULT 1,
            created_by        uuid        NULL,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT clinics_pkey PRIMARY KEY (clinic_id),
            CONSTRAINT clinics_created_by_fkey FOREIGN KEY (created_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT clinics_clinic_name_check CHECK (btrim(clinic_name) <> ''),
            CONSTRAINT clinics_origin_check CHECK (origin IN ('manual', 'import', 'inquiry')),
            -- Proposed Phase 1 vocabulary (SNX-20 approval gate); NULL means unknown. Widen in a new revision.
            CONSTRAINT clinics_status_code_check CHECK (
                status_code IN ('contacted', 'proposal_sent', 'awaiting_demo', 'follow_up_needed', 'closed')
            ),
            CONSTRAINT clinics_version_check CHECK (version >= 1)
        )
        """
    )
    op.execute("CREATE INDEX clinics_next_action_date_idx ON app.clinics (next_action_date)")
    op.execute(
        """
        CREATE TRIGGER clinics_bump_row_version
            BEFORE UPDATE ON app.clinics
            FOR EACH ROW EXECUTE FUNCTION app.bump_row_version()
        """
    )
    op.execute(
        "COMMENT ON TABLE app.clinics IS "
        "'Confirmed clinic leads. Staff edits are authoritative; re-imports and dbt never overwrite them.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.clinics")
