-- silver.leads grain: one row per (record_type, lead_id). Returns duplicates; zero rows passes.
select record_type, lead_id, count(*) as row_count
from {{ ref('leads') }}
group by record_type, lead_id
having count(*) > 1
