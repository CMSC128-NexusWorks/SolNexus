-- Current linked / needs_review decision per message, written by the API and resolution job.
select
    raw_message_id,
    resolution_status,
    clinic_id,
    review_reason
from {{ source('app', 'message_resolutions') }}
