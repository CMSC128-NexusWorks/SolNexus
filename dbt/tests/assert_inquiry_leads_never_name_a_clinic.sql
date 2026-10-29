-- An inquiry lead must show "Clinic name unknown": no clinic name, no clinic link, and no
-- linked activity. Returns violating rows; zero rows passes.
select lead_id, clinic_name, clinic_name_state, clinic_id, interaction_count
from {{ ref('leads') }}
where record_type = 'inquiry'
  and (
      clinic_name is not null
      or clinic_name_state <> 'unknown'
      or clinic_id is not null
      or interaction_count <> 0
  )
