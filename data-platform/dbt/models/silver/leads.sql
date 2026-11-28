-- silver.leads: one row per confirmed clinic or open inquiry, unique on (record_type, lead_id).
--
-- Operational fields come from app unchanged: staff edits live in app, and silver is rebuilt
-- from scratch on every run, so a value "fixed" here would be lost and could hide a staff edit.
-- Columns follow docs/contracts/phase1-erd-schema-draft.md, plus the fields the export needs.

with clinics as (
    select * from {{ ref('stg_app__clinics') }}
),

inquiries as (
    select * from {{ ref('stg_app__lead_inquiries') }}
),

interactions as (
    select * from {{ ref('interactions') }}
),

clinic_activity as (
    -- Only links that passed both checks in silver.interactions count toward a clinic.
    select
        clinic_id,
        -- max() skips null event_at, so a message without a provider time adds to the count
        -- but never becomes the last contact (sync time is not conversation time).
        max(event_at) as last_interaction_at,
        -- int, not count()'s bigint: the ERD declares interaction_count int.
        cast(count(*) as int) as interaction_count
    from interactions
    where is_linked
    group by clinic_id
),

clinic_leads as (
    select
        c.clinic_id as lead_id,
        'clinic' as record_type,
        c.clinic_id,
        c.clinic_name,
        'confirmed' as clinic_name_state,
        c.contact_person,
        c.person_spoken_to,
        c.calling_notes,
        c.contact_number,
        c.email,
        c.region,
        c.province,
        c.municipality,
        c.address,
        c.status_code,
        c.next_action_date,
        c.next_step,
        c.point_person,
        c.discovery_source,
        c.origin,
        c.version,
        a.last_interaction_at,
        -- LEFT join + coalesce: clinics with no messages (e.g. imported or manual) still appear.
        coalesce(a.interaction_count, 0) as interaction_count
    from clinics as c
    left join clinic_activity as a
        on a.clinic_id = c.clinic_id
),

inquiry_leads as (
    -- Open inquiries only. A confirmed inquiry is closed and reappears as its clinic, so
    -- including closed ones would show the same lead twice.
    select
        i.inquiry_id as lead_id,
        'inquiry' as record_type,
        cast(null as uuid) as clinic_id,
        -- Never guessed: the dashboard renders this as "Clinic name unknown".
        cast(null as text) as clinic_name,
        i.clinic_name_state,
        i.contact_person,
        cast(null as text) as person_spoken_to,
        i.calling_notes,
        i.contact_number,
        i.email,
        cast(null as text) as region,
        cast(null as text) as province,
        cast(null as text) as municipality,
        cast(null as text) as address,
        i.status_code,
        i.next_action_date,
        i.next_step,
        cast(null as text) as point_person,
        cast(null as text) as discovery_source,
        'inquiry' as origin,
        i.version,
        -- Inquiry messages are unlinked (no clinic yet), and only linked interactions count.
        cast(null as timestamptz) as last_interaction_at,
        0 as interaction_count
    from inquiries as i
    where i.state = 'open'
)

select * from clinic_leads
union all
select * from inquiry_leads
