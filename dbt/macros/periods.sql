{# 'YYYY-MM' period string from a date #}
{% macro period_of(col) -%}{{ return(adapter.dispatch('period_of', 'planwerk')(col)) }}{%- endmacro %}
{% macro duckdb__period_of(col) -%}strftime({{ col }}, '%Y-%m'){%- endmacro %}
{% macro snowflake__period_of(col) -%}to_char({{ col }}, 'YYYY-MM'){%- endmacro %}
{% macro default__period_of(col) -%}to_char({{ col }}, 'YYYY-MM'){%- endmacro %}

{# period string from fiscal year and 3-digit posting period #}
{% macro period_from_parts(year_col, poper_col) -%}
    {{ dbt.concat([year_col, "'-'", dbt.right(poper_col, 2)]) }}
{%- endmacro %}

{# ISO date from a 'YYYY-MM-DD' string #}
{% macro to_date(col) -%}cast({{ col }} as date){%- endmacro %}

{# week start (Monday) #}
{% macro week_start(col) -%}{{ return(adapter.dispatch('week_start', 'planwerk')(col)) }}{%- endmacro %}
{% macro duckdb__week_start(col) -%}cast(date_trunc('week', {{ col }}) as date){%- endmacro %}
{% macro snowflake__week_start(col) -%}cast(date_trunc('week', {{ col }}) as date){%- endmacro %}
{% macro default__week_start(col) -%}cast(date_trunc('week', {{ col }}) as date){%- endmacro %}
