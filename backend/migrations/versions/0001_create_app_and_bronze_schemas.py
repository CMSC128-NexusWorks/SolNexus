"""Create the app and bronze schemas.

Revision ID: 0001
Revises:
Create Date: 2026-10-27
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: a scaffold volume may already hold an empty schema created by hand or by dbt.
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    op.execute("COMMENT ON SCHEMA app IS 'Durable operational state written by the API and ingestion. Alembic-owned.'")
    op.execute("COMMENT ON SCHEMA bronze IS 'Append-only source evidence. Alembic-owned; dbt may read but never write.'")


def downgrade() -> None:
    # No CASCADE: fail loudly instead of silently dropping data a later revision left behind.
    op.execute("DROP SCHEMA bronze")
    op.execute("DROP SCHEMA app")
