-- Semantic view: DB I and PVM effects per product group, year to date, constant currency.
select c.fiscal_year as jahr, c.to_month as bis_monat, c.company_code as bereich, c.material_group as produktgruppe,
       case c.material_group when 'PG10' then 'Kreiselpumpen' when 'PG20' then 'Dosierpumpen'
            when 'PG30' then 'Ventile und Armaturen' when 'PG40' then 'Ersatzteile' else 'Service' end as produktgruppe_text,
       sum(c.revenue_ist) as ist_umsatz_eur, sum(c.revenue_plan) as plan_umsatz_eur,
       sum(c.db1_ist) as ist_db1_eur, sum(c.db1_plan) as plan_db1_eur,
       sum(c.price_effect) as preiseffekt_eur, sum(c.volume_effect) as mengeneffekt_eur,
       sum(c.mix_effect) as mixeffekt_eur, sum(c.var_cost_effect) as materialkosteneffekt_eur
from {{ ref('mart_pvm_cells') }} c
group by all
