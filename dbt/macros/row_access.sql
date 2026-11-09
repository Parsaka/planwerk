{#
  Row-level security per cost-centre owner.
  * Snowflake: a ROW ACCESS POLICY on the cost-centre marts, mapping CURRENT_USER() to the
    cost centres in reference.cost_centre_access (controllers and management see all).
  * DuckDB (local): the semantic view filters on the session variable planwerk_user
    (SET VARIABLE planwerk_user = '...'), default var('planwerk_user'), so the same logic can
    be tested without Snowflake.
#}
{% macro current_planwerk_user() -%}
    {%- if target.type == 'snowflake' -%}current_user(){%- else -%}coalesce(getvariable('planwerk_user'), '{{ var("planwerk_user") }}'){%- endif -%}
{%- endmacro %}

{% macro cost_centre_policy_body() -%}
    is_role_in_session('{{ target.role | upper }}')
        or exists (select 1 from {{ ref('cost_centre_access') }} a
                   where upper(a.user_name) = current_user()
                     and (a.cost_centre = '*' or a.cost_centre = cc))
{%- endmacro %}

{# The building role (dbt, target.role) is exempt: otherwise dbt's own tests and every downstream
   model would read zero rows from the protected mart, because the service user is not a
   cost-centre owner. Everyone else sees the cost centres listed for their user name. #}
{% macro apply_cost_centre_policy(relation, column='cost_centre') %}
  {% if target.type == 'snowflake' %}
    {% set policy = relation.database ~ '.' ~ relation.schema ~ '.rap_cost_centre' %}
    create row access policy if not exists {{ policy }}
      as (cc varchar) returns boolean -> {{ cost_centre_policy_body() }};
    alter row access policy {{ policy }} set body -> {{ cost_centre_policy_body() }};
    alter table {{ relation }} add row access policy {{ policy }} on ({{ column }});
  {% else %}
    select 1
  {% endif %}
{% endmacro %}
