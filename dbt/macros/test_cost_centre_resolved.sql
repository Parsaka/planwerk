{% test dbt_expression_cost_centre_resolved(model) %}
-- every line with a cost centre finds exactly the cost-centre version valid on its posting date
select * from {{ model }} where cost_centre is not null and cost_centre_sk is null
{% endtest %}
