select
    *,
    revenue_eur - var_cost_eur       as db1_eur,
    revenue_cc_eur - var_cost_cc_eur as db1_cc_eur
from {{ ref('int_sales_items_costed') }}
