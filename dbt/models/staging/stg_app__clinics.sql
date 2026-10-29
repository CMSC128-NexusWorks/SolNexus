-- Confirmed clinic leads. Operational fields are owned by the API and import, so they pass
-- through unchanged: silver must never overwrite or "fill in" a staff edit.
select
    clinic_id,
    clinic_name,
    contact_person,
    person_spoken_to,
    calling_notes,
    contact_number,
    email,
    region,
    province,
    municipality,
    address,
    status_code,
    next_action_date,
    next_step,
    point_person,
    discovery_source,
    origin,
    version,
    created_at,
    updated_at
from {{ source('app', 'clinics') }}
