-- silver.interactions: one row per bronze message, unique on raw_message_id.
--
-- clinic_id is set only when BOTH hold (docs/database.md "Silver contract"):
--   1. the message's app.message_resolutions row is 'linked', and
--   2. an ACTIVE app.clinic_source_identities mapping for the message's exact
--      (source_channel, source_account_id, external_participant_id) points to that same clinic.
-- Check 2 guards against a stale resolution: after staff revoke or correct a mapping, the
-- resolution job re-checks messages in batches, and until it does, the old 'linked' row must
-- not keep the message in the wrong clinic's history.

with messages as (
    select * from {{ ref('stg_bronze__raw_messages') }}
),

resolutions as (
    select * from {{ ref('stg_app__message_resolutions') }}
),

active_mappings as (
    -- At most one active mapping per source key (partial unique index), so joining on the
    -- key cannot duplicate a message row.
    select * from {{ ref('stg_app__clinic_source_identities') }}
    where is_active
),

joined as (
    select
        m.raw_message_id,
        m.source_channel,
        m.source_account_id,
        m.source_message_id,
        m.source_thread_id,
        m.external_participant_id,
        m.direction,
        m.source_event_at,
        m.ingested_at,
        -- Null when the resolution job has not processed the message yet.
        r.resolution_status,
        r.review_reason,
        r.clinic_id as resolved_clinic_id,
        am.mapping_id as active_mapping_id,
        -- Both checks pass only when the active mapping names the clinic the resolution chose.
        (r.resolution_status = 'linked' and am.clinic_id = r.clinic_id) is true as is_linked
    from messages as m
    -- LEFT joins: every message stays in silver, linked or not, so nothing silently disappears.
    left join resolutions as r
        on r.raw_message_id = m.raw_message_id
    left join active_mappings as am
        on  am.source_channel = m.source_channel
        and am.source_account_id = m.source_account_id
        and am.external_participant_id = m.external_participant_id
)

select
    raw_message_id,
    source_channel as channel,
    source_account_id,
    source_message_id,
    source_thread_id,
    external_participant_id,
    direction,
    -- Provider event time only; never replaced by ingested_at, because sync time is not
    -- conversation time (contract: last_contact_at must come from a trustworthy event time).
    source_event_at as event_at,
    ingested_at,
    resolution_status,
    review_reason,
    is_linked,
    case when is_linked then resolved_clinic_id end as clinic_id,
    case when is_linked then active_mapping_id end as mapping_id
from joined
