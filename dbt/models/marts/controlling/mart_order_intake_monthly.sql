-- Order intake vs billing per period: leading indicator for the rolling forecast (Q2)
with oi as (
    select period, company_code, material_group, sum(net_value_eur) as order_intake_eur, count(*) as order_items
    from {{ ref('fct_order_intake') }} group by all
),
rev as (
    select period, company_code, material_group, sum(revenue_eur) as revenue_eur
    from {{ ref('fct_sales_item') }} group by all
)
select coalesce(oi.period, rev.period) as period, coalesce(oi.company_code, rev.company_code) as company_code,
       coalesce(oi.material_group, rev.material_group) as material_group,
       coalesce(oi.order_intake_eur, 0) as order_intake_eur, coalesce(oi.order_items, 0) as order_items,
       coalesce(rev.revenue_eur, 0) as revenue_eur
from oi full outer join rev
  on oi.period = rev.period and oi.company_code = rev.company_code and oi.material_group = rev.material_group
