"""Create app.import_batches and app.import_rows.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-28
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per workbook upload (FR-02). Stores the file hash, never the private workbook itself.
    # An equal hash is a replay hint only, so it is indexed but not unique.
    op.execute(
        """
        CREATE TABLE app.import_batches (
            batch_id               uuid        NOT NULL DEFAULT gen_random_uuid(),
            uploaded_by            uuid        NOT NULL,
            file_sha256            text        NOT NULL,
            original_filename      text        NOT NULL,
            uploaded_at            timestamptz NOT NULL DEFAULT now(),
            state                  text        NOT NULL DEFAULT 'processing',
            created_clinic_count   integer     NOT NULL DEFAULT 0,
            accepted_row_count     integer     NOT NULL DEFAULT 0,
            needs_review_row_count integer     NOT NULL DEFAULT 0,
            rejected_row_count     integer     NOT NULL DEFAULT 0,
            skipped_row_count      integer     NOT NULL DEFAULT 0,
            CONSTRAINT import_batches_pkey PRIMARY KEY (batch_id),
            CONSTRAINT import_batches_uploaded_by_fkey
                FOREIGN KEY (uploaded_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT import_batches_file_sha256_check CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT import_batches_state_check CHECK (state IN ('processing', 'needs_review', 'completed', 'failed')),
            CONSTRAINT import_batches_counts_check CHECK (
                created_clinic_count >= 0 AND accepted_row_count >= 0 AND needs_review_row_count >= 0
                AND rejected_row_count >= 0 AND skipped_row_count >= 0
            )
        )
        """
    )
    op.execute("CREATE INDEX import_batches_file_sha256_idx ON app.import_batches (file_sha256)")

    # One result per attempted workbook row. Accepted rows link a clinic; other results have none
    # until review accepts them. Two accepted rows may link the same clinic (cross-sheet match).
    op.execute(
        """
        CREATE TABLE app.import_rows (
            import_row_id     uuid    NOT NULL DEFAULT gen_random_uuid(),
            batch_id          uuid    NOT NULL,
            sheet_name        text    NOT NULL,
            row_number        integer NOT NULL,
            row_fingerprint   text    NOT NULL,
            normalized_fields jsonb   NOT NULL DEFAULT '{}'::jsonb,
            validation_errors jsonb   NOT NULL DEFAULT '[]'::jsonb,
            result            text    NOT NULL,
            clinic_id         uuid    NULL,
            CONSTRAINT import_rows_pkey PRIMARY KEY (import_row_id),
            CONSTRAINT import_rows_batch_row_key UNIQUE (batch_id, sheet_name, row_number),
            CONSTRAINT import_rows_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES app.import_batches (batch_id),
            CONSTRAINT import_rows_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT import_rows_sheet_name_check CHECK (btrim(sheet_name) <> ''),
            CONSTRAINT import_rows_row_number_check CHECK (row_number >= 1),
            CONSTRAINT import_rows_result_check CHECK (result IN ('accepted', 'needs_review', 'rejected', 'skipped')),
            CONSTRAINT import_rows_clinic_check CHECK ((result = 'accepted') = (clinic_id IS NOT NULL)),
            CONSTRAINT import_rows_normalized_fields_check CHECK (jsonb_typeof(normalized_fields) = 'object'),
            CONSTRAINT import_rows_validation_errors_check CHECK (jsonb_typeof(validation_errors) = 'array')
        )
        """
    )
    op.execute("CREATE INDEX import_rows_fingerprint_idx ON app.import_rows (row_fingerprint)")
    op.execute("CREATE INDEX import_rows_clinic_id_idx ON app.import_rows (clinic_id)")
    op.execute(
        "COMMENT ON COLUMN app.import_rows.normalized_fields IS "
        "'Client row values. Restricted import evidence; retention period pending SNX-20 approval.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.import_rows")
    op.execute("DROP TABLE app.import_batches")
