-- Every parser suggestion must say which rule set produced it, so a later rule change can be
-- traced and re-run. Returns suggestions without a parser_version; zero rows passes.
select raw_message_id, topic, derived_status_code
from {{ ref('interactions') }}
where (topic is not null or derived_status_code is not null)
  and parser_version is null
