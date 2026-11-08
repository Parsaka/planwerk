-- One row per billed sales order item with revenue, matched variable cost and the plan
-- reference values (plan price, standard cost) needed for the price-volume-mix analysis.
with bill as (
    select * from {{ ref('stg_s4__billing_items') }}
),
orders as (
    select sales_order, sales_order_item, order_date, customer_group
    from {{ ref('stg_s4__sales_order_items') }}
),
revenue as (
    select sales_order, sales_order_item,
           -sum(amount_lc)  as revenue_lc,
           -sum(amount_eur) as revenue_eur
    from {{ ref('stg_s4__journal_lines') }}
    where gl_account in ('400000', '405000') and sales_order is not null
    group by sales_order, sales_order_item
),
var_cost as (
    -- component consumption of the make-to-order production order (WA) and trading goods
    -- issued with the delivery (WL, 503000); finished-goods issues at standard (480000) are
    -- inventory movements, not variable cost
    select sales_order, sales_order_item,
           sum(amount_lc)  as var_cost_lc,
           sum(amount_eur) as var_cost_eur
    from {{ ref('stg_s4__journal_lines') }}
    where gl_account in ('500000', '501000', '502000', '503000') and sales_order is not null
    group by sales_order, sales_order_item
),
base as (
    select
        b.billing_document, b.billing_item, b.period,
        cast(left(b.period, 4) as integer) as fiscal_year,
        cast(right(b.period, 2) as integer) as fiscal_month,
        b.company_code, b.customer, o.customer_group, b.material, b.material_group, b.quantity,
        b.sales_order, b.sales_order_item, o.order_date,
        greatest(cast(extract(year from o.order_date) as integer), 2023) as price_year
    from bill b
    join orders o on o.sales_order = b.sales_order and o.sales_order_item = b.sales_order_item
)
select
    base.*,
    r.revenue_lc,
    r.revenue_eur,
    coalesce(v.var_cost_lc, 0)  as var_cost_lc,
    coalesce(v.var_cost_eur, 0) as var_cost_eur,
    -- plan price: price list the budget assumed for orders of the budget year, the actual
    -- price list for backlog orders from earlier years (known when the budget was set)
    pl.list_price * (1 - d.discount_rate) as plan_price_lc,
    case when base.material_group = 'PG50' then 0 else coalesce(sp.standard_price_eur, 0) end as standard_cost_eur,
    fx.actual_rate,
    fx.plan_rate,
    -- constant currency (plan FX) values in EUR
    r.revenue_lc / fx.plan_rate                                           as revenue_cc_eur,
    coalesce(v.var_cost_lc, 0) / fx.plan_rate                             as var_cost_cc_eur,
    base.quantity * pl.list_price * (1 - d.discount_rate) / fx.plan_rate  as revenue_at_plan_price_cc_eur,
    base.quantity * case when base.material_group = 'PG50' then 0
                         else coalesce(sp.standard_price_eur, 0) end      as standard_cost_cc_eur
from base
join revenue r on r.sales_order = base.sales_order and r.sales_order_item = base.sales_order_item
left join var_cost v on v.sales_order = base.sales_order and v.sales_order_item = base.sales_order_item
join {{ ref('stg_s4__price_list') }} pl
  on pl.material = base.material and pl.sales_org = base.company_code and pl.price_year = base.price_year
 and pl.price_version = case when base.price_year < base.fiscal_year then 'ACT' else 'PLN' end
join {{ ref('stg_s4__discount_conditions') }} d on d.customer_group = base.customer_group
left join {{ ref('stg_s4__standard_prices') }} sp
  on sp.material = base.material and sp.fiscal_year = base.fiscal_year
join {{ ref('int_fx_rates') }} fx on fx.company_code = base.company_code and fx.period = base.period
