-- Actual (ECB monthly average) and plan rate per company code and period. EUR company codes = 1.
with periods as (
    select period, eur_pln from {{ ref('stg_ext__drivers') }}
    where period between '{{ var("first_period") }}' and '{{ var("last_period") }}'
),
plan as (
    select fiscal_year, max(plan_fx_eur_pln) as plan_eur_pln
    from {{ ref('stg_s4__plan_lines') }} group by fiscal_year
)
select
    c.company_code,
    p.period,
    cast(left(p.period, 4) as integer) as fiscal_year,
    case when c.local_currency = 'PLN' then p.eur_pln else 1.0 end as actual_rate,
    case when c.local_currency = 'PLN' then pl.plan_eur_pln else 1.0 end as plan_rate
from periods p
cross join (select distinct company_code, local_currency from {{ ref('stg_s4__company_codes') }}) c
join plan pl on pl.fiscal_year = cast(left(p.period, 4) as integer)
