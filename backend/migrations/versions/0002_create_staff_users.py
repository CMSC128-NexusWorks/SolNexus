"""Create app.staff_users.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # citext compares case-insensitively, so Staff@Example.test and staff@example.test are one account.
    # Installed in public so the type resolves on the default search_path for every role.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public")
    op.execute(
        """
        CREATE TABLE app.staff_users (
            user_id       uuid        NOT NULL DEFAULT gen_random_uuid(),
            email         citext      NOT NULL,
            password_hash text        NOT NULL,
            is_active     boolean     NOT NULL DEFAULT true,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT staff_users_pkey PRIMARY KEY (user_id),
            CONSTRAINT staff_users_email_key UNIQUE (email),
            CONSTRAINT staff_users_email_check CHECK (email ~ '^[^@\\s]+@[^@\\s]+$'),
            -- Argon2 and bcrypt hashes are PHC/modular-crypt strings starting with '$'; rejects plain text.
            CONSTRAINT staff_users_password_hash_check CHECK (password_hash LIKE '$%')
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE app.staff_users IS "
        "'SolTech dashboard accounts. Deactivate with is_active; never delete, audit rows reference user_id.'"
    )


def downgrade() -> None:
    # Leave citext installed: other objects may depend on it, and it holds no data.
    op.execute("DROP TABLE app.staff_users")
