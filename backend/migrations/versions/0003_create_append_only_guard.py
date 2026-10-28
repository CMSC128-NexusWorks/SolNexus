"""Create the shared append-only guard trigger function.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Attached BEFORE UPDATE/DELETE (row) and BEFORE TRUNCATE (statement) on evidence and audit tables.
    # Triggers bind every role, including the shared superuser, so this stops accidents; it is not
    # tamper-proof, since an owner can DISABLE TRIGGER. Least-privilege roles are a separate follow-up.
    op.execute(
        """
        CREATE FUNCTION app.reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            -- Concatenation, not RAISE '%' placeholders: offline `alembic upgrade --sql` doubles every '%'.
            RAISE EXCEPTION USING
                MESSAGE = TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is append-only: ' || TG_OP || ' rejected',
                ERRCODE = 'restrict_violation',
                HINT = 'Insert a new row instead. Maintenance must disable the trigger in a reviewed migration.';
        END
        $$
        """
    )


def downgrade() -> None:
    # No CASCADE: fails while any table still uses the guard.
    op.execute("DROP FUNCTION app.reject_mutation()")
