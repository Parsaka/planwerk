{#
  Row-level security per cost-centre owner.
  * Snowflake: a ROW ACCESS POLICY on the cost-centre marts, mapping CURRENT_USER() to the
    cost centres in reference.cost_centre_access (controllers and management see all).
  * DuckDB (local): the semantic view filters on var('planwerk_user') so the same logic can
    be tested without Snowflake.
#}
{% macro current_planwerk_user() -%}
    {%- if target.type == 'snowflake' -%}current_user(){%- else -%}'{{ var("planwerk_user") }}'{%- endif -%}
{%- endmacro %}

{% macro apply_cost_centre_policy(relation, column='cost_centre') %}
  {% if target.type == 'snowflake' %}
    create row access policy if not exists {{ relation.database }}.{{ relation.schema }}.rap_cost_centre
      as (cc varchar) returns boolean ->
        exists (select 1 from {{ ref('cost_centre_access') }} a
                where upper(a.user_name) = current_user()
                  and (a.cost_centre = '*' or a.cost_centre = cc));
    alter table {{ relation }} add row access policy {{ relation.database }}.{{ relation.schema }}.rap_cost_centre on ({{ column }});
  {% else %}
    select 1
  {% endif %}
{% endmacro %}
