{# md5 surrogate key without a package dependency (same idea as dbt_utils.generate_surrogate_key) #}
{% macro dbt_utils_surrogate(cols) -%}
    md5({%- for c in cols -%}coalesce(cast({{ c }} as varchar), '_null_'){% if not loop.last %} || '|' || {% endif %}{%- endfor -%})
{%- endmacro %}
