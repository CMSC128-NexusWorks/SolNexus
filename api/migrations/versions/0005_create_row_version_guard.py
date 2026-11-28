"""Create the shared row-version guard trigger function.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Optimistic concurrency for staff-editable rows. The API updates with
    #   SET ..., version = version + 1 WHERE <id> = :id AND version = :expected
    # and returns 409 when no row matches. This trigger rejects any writer that forgets the bump,
    # which would otherwise let a later stale edit silently overwrite this one.
    op.execute(
        """
        CREATE FUNCTION app.bump_row_version() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.version IS DISTINCT FROM OLD.version + 1 THEN
                RAISE EXCEPTION USING
                    MESSAGE = TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' update must set version = version + 1',
                    ERRCODE = 'check_violation';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION app.bump_row_version()")
