-- Semantic view: fixed-cost variance per cost centre and account, year to date.
select v.fiscal_year as jahr, v.to_month as bis_monat, v.company_code as bereich, v.cost_centre as kostenstelle,
       v.cost_centre_name as kostenstelle_text, v.gl_account as konto, v.gl_account_text as konto_text,
       v.plan_cc_eur as plan_eur, v.actual_cc_eur as ist_eur, v.variance_cc_eur as abweichung_eur
from {{ ref('mart_cost_variance') }} v
where exists (
    select 1 from {{ ref('cost_centre_access') }} a
    where lower(a.user_name) = lower({{ current_planwerk_user() }})
      and (a.cost_centre = '*' or cast(a.cost_centre as varchar) = v.cost_centre)
)
