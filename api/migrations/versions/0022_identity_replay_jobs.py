"""SNX-30 durable bounded replay after staff inquiry confirmation."""

from alembic import op

revision = "0022"
down_revision = "0020"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app.identity_replay_jobs (
      job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      mapping_id uuid NOT NULL REFERENCES app.clinic_source_identities(mapping_id),
      changed_by uuid NOT NULL REFERENCES app.staff_users(user_id),
      after_id uuid NULL, state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','complete','superseded')),
      created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz NULL)""")


def downgrade():
    op.execute("DROP TABLE app.identity_replay_jobs")
