-- First contacts whose clinic name is still unknown. Closed inquiries are kept here and
-- filtered in silver.leads, so staging keeps one row per source row.
select
    inquiry_id,
    clinic_name_state,
    contact_person,
    contact_number,
    email,
    status_code,
    next_action_date,
    next_step,
    calling_notes,
    state,
    version
from {{ source('app', 'lead_inquiries') }}
