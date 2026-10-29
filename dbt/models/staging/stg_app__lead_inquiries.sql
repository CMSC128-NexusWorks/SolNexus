-- First contacts whose clinic name is still unknown. Closed inquiries are kept here and
-- filtered in silver.leads, so staging stays a plain 1:1 view of the source.
select
    inquiry_id,
    source_channel,
    source_account_id,
    external_participant_id,
    origin_raw_message_id,
    clinic_name_state,
    contact_person,
    contact_number,
    email,
    status_code,
    next_action_date,
    next_step,
    calling_notes,
    state,
    confirmed_clinic_id,
    version,
    created_at,
    updated_at
from {{ source('app', 'lead_inquiries') }}
