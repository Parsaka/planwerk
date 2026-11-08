-- ADR-0001 Q1 criterion 3: >= 90 % of the absolute fixed-cost deviation sits on named cost centres
with v as (
    select sum(abs(variance_cc_eur)) as total,
           sum(case when cost_centre is not null and cost_centre_name is not null then abs(variance_cc_eur) else 0 end) as named
    from {{ ref('mart_cost_variance') }} where to_month = 12
)
select * from v where total > 0 and named / total < 0.9
