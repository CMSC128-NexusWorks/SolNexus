"""Create app.clinic_source_identities.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Staff-confirmed link from one exact source identity key to one clinic. This is the only thing
    # that may link a message to a clinic; names, phones and imported contacts never create one.
    op.execute(
        """
        CREATE TABLE app.clinic_source_identities (
            mapping_id              uuid        NOT NULL DEFAULT gen_random_uuid(),
            source_channel          text        NOT NULL,
            source_account_id       text        NOT NULL,
            external_participant_id text        NOT NULL,
            clinic_id               uuid        NOT NULL,
            confirmed_by            uuid        NOT NULL,
            confirmed_at            timestamptz NOT NULL DEFAULT now(),
            reason                  text        NULL,
            revoked_at              timestamptz NULL,
            revoked_by              uuid        NULL,
            revoke_reason           text        NULL,
            CONSTRAINT clinic_source_identities_pkey PRIMARY KEY (mapping_id),
            CONSTRAINT clinic_source_identities_clinic_id_fkey
                FOREIGN KEY (clinic_id) REFERENCES app.clinics (clinic_id),
            CONSTRAINT clinic_source_identities_confirmed_by_fkey
                FOREIGN KEY (confirmed_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT clinic_source_identities_revoked_by_fkey
                FOREIGN KEY (revoked_by) REFERENCES app.staff_users (user_id),
            CONSTRAINT clinic_source_identities_source_channel_check CHECK (source_channel IN ('gmail')),
            -- A mapping needs the complete key; an incomplete identity can only ever be needs_review.
            CONSTRAINT clinic_source_identities_source_key_check CHECK (
                btrim(source_account_id) <> '' AND btrim(external_participant_id) <> ''
            ),
            CONSTRAINT clinic_source_identities_revocation_check CHECK (
                (revoked_at IS NULL) = (revoked_by IS NULL) AND (revoked_at IS NULL OR revoked_at >= confirmed_at)
            )
        )
        """
    )
    # At most one active mapping per key; revoked rows remain as history.
    op.execute(
        """
        CREATE UNIQUE INDEX clinic_source_identities_active_key ON app.clinic_source_identities
            (source_channel, source_account_id, external_participant_id)
            WHERE revoked_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX clinic_source_identities_clinic_id_idx ON app.clinic_source_identities (clinic_id)"
    )

    # Correction = revoke the old row, insert a new one. The only permitted UPDATE sets the revocation
    # fields once on an active row; everything else about a confirmation is immutable.
    op.execute(
        """
        CREATE FUNCTION app.guard_mapping_revocation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.revoked_at IS NOT NULL
               OR NEW.revoked_at IS NULL
               OR (NEW.mapping_id, NEW.source_channel, NEW.source_account_id, NEW.external_participant_id,
                   NEW.clinic_id, NEW.confirmed_by, NEW.confirmed_at, NEW.reason)
                  IS DISTINCT FROM
                  (OLD.mapping_id, OLD.source_channel, OLD.source_account_id, OLD.external_participant_id,
                   OLD.clinic_id, OLD.confirmed_by, OLD.confirmed_at, OLD.reason)
            THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'app.clinic_source_identities: only revoking an active mapping is allowed; '
                              || 'insert a new mapping to correct a link',
                    ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_source_identities_revoke_only
            BEFORE UPDATE ON app.clinic_source_identities
            FOR EACH ROW EXECUTE FUNCTION app.guard_mapping_revocation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_source_identities_no_delete
            BEFORE DELETE ON app.clinic_source_identities
            FOR EACH ROW EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER clinic_source_identities_no_truncate
            BEFORE TRUNCATE ON app.clinic_source_identities
            FOR EACH STATEMENT EXECUTE FUNCTION app.reject_mutation()
        """
    )
    op.execute(
        "COMMENT ON TABLE app.clinic_source_identities IS "
        "'Staff-confirmed source identity to clinic links. Append history: revoke and insert, never edit.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE app.clinic_source_identities")
    op.execute("DROP FUNCTION app.guard_mapping_revocation()")
