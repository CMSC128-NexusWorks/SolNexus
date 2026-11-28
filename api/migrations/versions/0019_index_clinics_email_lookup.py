"""Index app.clinics by normalized email.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-30
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The Gmail connector looks up candidate clinics for every new message with
    # WHERE lower(btrim(email)) = :participant. An index on that exact expression turns the per-message
    # full scan of app.clinics into an index lookup once the workbook import has loaded many clinics.
    # Not unique: the workbook can hold several clinics with one email, which is what makes a message
    # 'multiple_candidates'.
    op.execute("CREATE INDEX clinics_email_lookup_idx ON app.clinics (lower(btrim(email)))")


def downgrade() -> None:
    op.execute("DROP INDEX app.clinics_email_lookup_idx")
