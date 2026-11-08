-- Semantic view: order intake and revenue per month, scope and product group (EUR).
select period as periode, cast(left(period, 4) as integer) as jahr, cast(right(period, 2) as integer) as monat,
       company_code as bereich, material_group as produktgruppe,
       order_intake_eur as auftragseingang_eur, revenue_eur as umsatz_eur
from {{ ref('mart_order_intake_monthly') }}
