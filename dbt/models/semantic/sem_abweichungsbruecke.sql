-- Semantic view: budget -> actual DB II bridge, year to date (positive = favourable).
select fiscal_year as jahr, to_month as bis_monat, scope as bereich,
       plan_db2_eur, volume_effect as mengeneffekt_eur, mix_effect as mixeffekt_eur, price_effect as preiseffekt_eur,
       var_cost_effect as materialkosteneffekt_eur, sales_deduction_effect as erloesschmaelerung_eur,
       fixed_cost_db2_effect as fixkosteneffekt_db2_eur, fx_effect_db2 as waehrungseffekt_eur,
       actual_db2_eur as ist_db2_eur,
       plan_operating_result_eur as plan_betriebsergebnis_eur, actual_operating_result_eur as ist_betriebsergebnis_eur
from {{ ref('mart_db2_bridge') }}
