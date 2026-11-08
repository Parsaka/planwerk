-- Long KPI table (one row per period, scope, KPI) with actual, plan and variance. Feeds the
-- semantic layer of the AI assistant and the Excel report.
with s as (
    select version, period, fiscal_year, fiscal_month, company_code as scope,
           revenue_eur, net_revenue_eur, var_cost_eur, db1_eur, fix_db2_eur, db2_eur, fix_db3_eur, db3_eur,
           fix_unt_eur, operating_result_eur
    from {{ ref('mart_db_statement_monthly') }}
    union all
    select version, period, fiscal_year, fiscal_month, 'GRUPPE',
           sum(revenue_eur), sum(net_revenue_eur), sum(var_cost_eur), sum(db1_eur), sum(fix_db2_eur), sum(db2_eur),
           sum(fix_db3_eur), sum(db3_eur), sum(fix_unt_eur), sum(operating_result_eur)
    from {{ ref('mart_db_statement_monthly') }} group by version, period, fiscal_year, fiscal_month
),
{% set kpis = [('umsatz', 'revenue_eur'), ('nettoumsatz', 'net_revenue_eur'), ('variable_kosten', 'var_cost_eur'),
               ('db1', 'db1_eur'), ('fixkosten_db2', 'fix_db2_eur'), ('db2', 'db2_eur'),
               ('fixkosten_db3', 'fix_db3_eur'), ('db3', 'db3_eur'), ('unternehmensfixkosten', 'fix_unt_eur'),
               ('betriebsergebnis', 'operating_result_eur')] %}
long as (
    {% for k, col in kpis %}
    select version, period, fiscal_year, fiscal_month, scope, '{{ k }}' as kpi, {{ col }} as value from s
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)
select i.period, i.fiscal_year, i.fiscal_month, i.scope, i.kpi,
       i.value as actual_eur, p.value as plan_eur, i.value - p.value as variance_eur,
       case when p.value <> 0 then (i.value - p.value) / abs(p.value) end as variance_pct
from long i
join long p on p.version = 'PLAN' and p.period = i.period and p.scope = i.scope and p.kpi = i.kpi
where i.version = 'IST'
