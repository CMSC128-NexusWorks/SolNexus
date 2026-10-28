"""Create app.import_field_reviews and its candidate rows.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-28
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Staff decision on conflicting values from two or more import rows (no sheet wins automatically).
    # clinic_id is NULL for a clinic-name conflict raised before the clinic exists.
    op.execute(
        """
        CREATE TABLE app.import_field_reviews (
            review_id         uuid                NOT NULL DEFAULT gen_random_uuid(),
            clinic_id         uuid                NULL,
            field_name        app.lead_field_name NOT NULL,
            state             text                NOT NULL DEFAULT 'unresolved',
            -- JSON null is a staff-selected empty value; SQL NULL means not yet resolved.
            resolved_value    jsonb               NULL,
            resolved_by       uuid                NULL,
            resolved_at       timestamptz         NULL,
            resolution_reason text                NULL,
            created_at        timestamptz         NOT NULL DEFAULT now(),
            CONSTRAINT import_field_reviews_pkey PRIMARY KEY (review_id),
            CONSTRAINT import_field_reviews_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT import_field_reviews_resolved_by_fkey
                FOREIGN KEY (resolved_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT import_field_reviews_state_check CHECK (state IN ('unresolved', 'resolved')),
            CONSTRAINT import_field_reviews_resolution_check CHECK (
                (state = 'resolved') = (resolved_value IS NOT NULL)
                AND (state = 'resolved') = (resolved_by IS NOT NULL)
                AND (state = 'resolved') = (resolved_at IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX import_field_reviews_clinic_id_idx ON app.import_field_reviews (clinic_id)")
    op.execute(
        """
        CREATE INDEX import_field_reviews_unresolved_idx ON app.import_field_reviews (created_at)
            WHERE state = 'unresolved'
        """
    )
    # Junction table instead of a uuid[] column so each candidate row is a real foreign key.
    op.execute(
        """
        CREATE TABLE app.import_field_review_candidates (
            review_id     uuid NOT NULL,
            import_row_id uuid NOT NULL,
            CONSTRAINT import_field_review_candidates_pkey PRIMARY KEY (review_id, import_row_id),
            CONSTRAINT import_field_review_candidates_review_id_fkey
                FOREIGN KEY (review_id) REFERENCES app.import_field_reviews (review_id),
            CONSTRAINT import_field_review_candidates_import_row_id_fkey
                FOREIGN KEY (import_row_id) REFERENCES app.import_rows (import_row_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX import_field_review_candidates_row_idx ON app.import_field_review_candidates (import_row_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.import_field_review_candidates")
    op.execute("DROP TABLE app.import_field_reviews")
