-- Order intake (Auftragseingang) at order-item grain, in EUR at the order month's ECB rate
select
    o.sales_order, o.sales_order_item, o.order_date, o.order_period as period, o.company_code,
    o.customer, o.customer_group, o.material, o.material_group, o.quantity, o.net_value as net_value_lc,
    o.net_value / coalesce(fx.actual_rate, d.eur_pln) as net_value_eur
from {{ ref('stg_s4__sales_order_items') }} o
left join {{ ref('int_fx_rates') }} fx on fx.company_code = o.company_code and fx.period = o.order_period
left join {{ ref('stg_ext__drivers') }} d on d.period = o.order_period and o.company_code = '3000'
where o.order_period <= '{{ var("last_period") }}'
