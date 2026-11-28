-- One row per bronze message, limited to the columns silver reads. Message content
-- (raw_payload_bytes and parsed_payload) is deliberately left out so no silver model can
-- expose it; the baseline-parser ticket adds parsed_payload when it needs it.
-- Identity columns are passed through exactly as stored: identity matching is exact
-- (phase1-identity-v1), so trimming or lower-casing here would create links staff never confirmed.
select
    raw_message_id,
    source_channel,
    source_account_id,
    source_message_id,
    source_thread_id,
    external_participant_id,
    direction,
    -- Null when the provider gave no event time; only this column may drive last-contact dates.
    source_event_at,
    ingested_at
from {{ source('bronze', 'raw_messages') }}
