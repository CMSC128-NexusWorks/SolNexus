"""Create app.import_row_decisions and record how each import row matched a clinic.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-30
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A staff decision on one or more `needs_review` import rows that the importer would not decide alone:
    # possible duplicates of each other or of an existing clinic (SNX-28). The contract requires the
    # actor, time, selected value and reason. Append-only: a later change of mind is a row edit or a new
    # import, never a rewrite of what was decided. selected_clinic_name is the staff-chosen name when the
    # grouped rows spelled it differently; it is restricted import evidence like import_rows values.
    op.execute(
        """
        CREATE TABLE app.import_row_decisions (
            decision_id          uuid        NOT NULL DEFAULT gen_random_uuid(),
            batch_id             uuid        NOT NULL,
            action               text        NOT NULL,
            clinic_id            uuid        NULL,
            selected_clinic_name text        NULL,
            reason               text        NOT NULL,
            decided_by           uuid        NOT NULL,
            decided_at           timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT import_row_decisions_pkey PRIMARY KEY (decision_id),
            CONSTRAINT import_row_decisions_batch_id_fkey
                FOREIGN KEY (batch_id) REFERENCES app.import_batches (batch_id),
            CONSTRAINT import_row_decisions_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT import_row_decisions_decided_by_fkey
                FOREIGN KEY (decided_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT import_row_decisions_action_check CHECK (action IN ('create_clinic', 'link_clinic', 'reject')),
            CONSTRAINT import_row_decisions_clinic_check CHECK ((action = 'reject') = (clinic_id IS NULL)),
            CONSTRAINT import_row_decisions_name_check CHECK (
                selected_clinic_name IS NULL
                OR (action = 'create_clinic' AND btrim(selected_clinic_name) <> '')
            ),
            CONSTRAINT import_row_decisions_reason_check CHECK (btrim(reason) <> '')
        )
        """
    )
    op.execute("CREATE INDEX import_row_decisions_batch_idx ON app.import_row_decisions (batch_id)")
    op.execute(
        """
        CREATE TRIGGER import_row_decisions_append_only
            BEFORE UPDATE OR DELETE ON app.import_row_decisions
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER import_row_decisions_no_truncate
            BEFORE TRUNCATE ON app.import_row_decisions
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )

    # match_basis says why an accepted row points at its clinic, so a re-import can tell a clinic this
    # workbook row created from one it was only linked to:
    #   new_clinic        the importer created the clinic; the row had no duplicate candidate
    #   prior_import      the same row (equal fingerprint) was accepted before; reuse that link, write nothing
    #   staff_new_clinic  staff decided the row(s) are a new clinic
    #   staff_link        staff linked the row(s) to an existing clinic
    # adapter_version is the sheet adapter that read the row; it is part of the fingerprint, so a new
    # adapter version never matches rows read by an old one.
    op.execute(
        """
        ALTER TABLE app.import_rows
            ADD COLUMN decision_id     uuid NULL,
            ADD COLUMN match_basis     text NULL,
            ADD COLUMN adapter_version text NULL,
            ADD CONSTRAINT import_rows_decision_id_fkey
                FOREIGN KEY (decision_id) REFERENCES app.import_row_decisions (decision_id)
        """
    )
    # Rows stored before this revision came only from the synthetic dev seed; no importer existed.
    op.execute("UPDATE app.import_rows SET match_basis = 'new_clinic' WHERE result = 'accepted'")
    op.execute(
        """
        ALTER TABLE app.import_rows
            ADD CONSTRAINT import_rows_match_basis_check CHECK (
                match_basis IN ('new_clinic', 'prior_import', 'staff_new_clinic', 'staff_link')
            ),
            ADD CONSTRAINT import_rows_match_basis_result_check CHECK ((result = 'accepted') = (match_basis IS NOT NULL)),
            ADD CONSTRAINT import_rows_staff_match_check CHECK (
                match_basis NOT IN ('staff_new_clinic', 'staff_link') OR decision_id IS NOT NULL
            )
        """
    )
    op.execute("CREATE INDEX import_rows_decision_id_idx ON app.import_rows (decision_id)")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.import_rows
            DROP COLUMN adapter_version,
            DROP COLUMN match_basis,
            DROP COLUMN decision_id
        """
    )
    op.execute("DROP TABLE app.import_row_decisions")
