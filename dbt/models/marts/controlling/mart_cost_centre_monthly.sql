-- Cost-centre report after the BAB: primary costs, allocations received and sent, total.
with prim as (
    select version, company_code, period, cost_centre,
           sum(amount_lc) as primary_lc, sum(amount_eur) as primary_eur, sum(amount_cc_eur) as primary_cc_eur
    from {{ ref('int_cost_centre_primary') }} group by all
),
recv as (
    select version, company_code, period, receiver as cost_centre,
           sum(amount_lc) as received_lc, sum(amount_eur) as received_eur, sum(amount_cc_eur) as received_cc_eur
    from {{ ref('int_bab_allocation') }} group by all
),
sent as (
    select version, company_code, period, sender as cost_centre,
           sum(amount_lc) as sent_lc, sum(amount_eur) as sent_eur, sum(amount_cc_eur) as sent_cc_eur
    from {{ ref('int_bab_allocation') }} group by all
),
keys as (
    select version, company_code, period, cost_centre from prim
    union select version, company_code, period, cost_centre from recv
),
cc as (
    select cost_centre, max(cost_centre_name) as cost_centre_name, max(cm_level) as cm_level
    from {{ ref('dim_cost_centre') }} group by cost_centre
)
select
    k.version, k.period, cast(left(k.period, 4) as integer) as fiscal_year,
    cast(right(k.period, 2) as integer) as fiscal_month,
    k.company_code, k.cost_centre, cc.cost_centre_name, cc.cm_level,
    coalesce(p.primary_lc, 0) as primary_lc, coalesce(p.primary_eur, 0) as primary_eur,
    coalesce(p.primary_cc_eur, 0) as primary_cc_eur,
    coalesce(r.received_lc, 0) as received_lc, coalesce(r.received_eur, 0) as received_eur,
    coalesce(r.received_cc_eur, 0) as received_cc_eur,
    coalesce(s.sent_lc, 0) as sent_lc, coalesce(s.sent_eur, 0) as sent_eur, coalesce(s.sent_cc_eur, 0) as sent_cc_eur,
    coalesce(p.primary_lc, 0) + coalesce(r.received_lc, 0) - coalesce(s.sent_lc, 0) as total_lc,
    coalesce(p.primary_eur, 0) + coalesce(r.received_eur, 0) - coalesce(s.sent_eur, 0) as total_eur,
    coalesce(p.primary_cc_eur, 0) + coalesce(r.received_cc_eur, 0) - coalesce(s.sent_cc_eur, 0) as total_cc_eur
from keys k
left join prim p using (version, company_code, period, cost_centre)
left join recv r using (version, company_code, period, cost_centre)
left join sent s using (version, company_code, period, cost_centre)
left join cc on cc.cost_centre = k.cost_centre
