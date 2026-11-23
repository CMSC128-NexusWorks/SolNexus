"""Create app.staff_sessions.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-28
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Server-side staff sessions (SNX-27). The cookie holds a random token; only its SHA-256 is stored,
    # so a database leak does not leak usable sessions. A session is valid while revoked_at is NULL,
    # expires_at (7 days from sign-in) has not passed and last_seen_at is within the 8-hour idle window.
    op.execute(
        """
        CREATE TABLE app.staff_sessions (
            session_id   uuid        NOT NULL DEFAULT gen_random_uuid(),
            user_id      uuid        NOT NULL,
            token_sha256 bytea       NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            expires_at   timestamptz NOT NULL,
            revoked_at   timestamptz NULL,
            CONSTRAINT staff_sessions_pkey PRIMARY KEY (session_id),
            CONSTRAINT staff_sessions_token_sha256_key UNIQUE (token_sha256),
            CONSTRAINT staff_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES app.staff_users (user_id),
            CONSTRAINT staff_sessions_token_sha256_check CHECK (octet_length(token_sha256) = 32),
            CONSTRAINT staff_sessions_expires_at_check CHECK (expires_at > created_at)
        )
        """
    )
    # Password resets revoke every session of one user.
    op.execute("CREATE INDEX staff_sessions_user_id_idx ON app.staff_sessions (user_id)")
    op.execute(
        "COMMENT ON TABLE app.staff_sessions IS "
        "'Staff sign-in sessions. Revoke with revoked_at; the cookie token itself is never stored.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.staff_sessions")
