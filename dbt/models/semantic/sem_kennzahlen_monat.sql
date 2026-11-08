-- Semantic view for the AI assistant: one row per month, scope and KPI (EUR).
-- scope: '1000' DE, '2000' AT, '3000' PL, 'GRUPPE' group.
select period as periode, fiscal_year as jahr, fiscal_month as monat, scope as bereich, kpi as kennzahl,
       actual_eur as ist_eur, plan_eur, variance_eur as abweichung_eur, variance_pct as abweichung_pct
from {{ ref('mart_kpi_monthly') }}
