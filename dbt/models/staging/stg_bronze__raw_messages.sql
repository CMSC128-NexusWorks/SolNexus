-- One row per bronze message, without the raw payload bytes.
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
    source_sender_id,
    -- Null when the provider gave no event time; only this column may drive last-contact dates.
    source_event_at,
    ingested_at,
    parsed_payload
from {{ source('bronze', 'raw_messages') }}
