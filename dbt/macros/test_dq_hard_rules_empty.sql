{% test dq_hard_rules_empty(model) %}
select * from {{ model }} where rule_id in ('DQ04', 'DQ06')
{% endtest %}
