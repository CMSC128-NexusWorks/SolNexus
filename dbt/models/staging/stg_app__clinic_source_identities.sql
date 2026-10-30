-- Staff-confirmed (channel, account, participant) -> clinic mappings, including revoked history.
select
    mapping_id,
    source_channel,
    source_account_id,
    external_participant_id,
    clinic_id,
    -- A partial unique index guarantees at most one active mapping per source key.
    revoked_at is null as is_active
from {{ source('app', 'clinic_source_identities') }}
