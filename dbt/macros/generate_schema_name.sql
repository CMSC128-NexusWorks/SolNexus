{#
  Use a model's +schema exactly (silver), instead of dbt's default "<target>_<schema>" (public_silver).
  The API and docs read silver.* by name, so the schema must not depend on the profile target.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
