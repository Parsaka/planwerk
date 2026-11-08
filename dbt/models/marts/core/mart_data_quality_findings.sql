-- Master-data quality checks in the style of SAP MDG validation rules. Every finding is a row.
-- The simulated data contains a few deliberate findings so that the checks are proven to work.
with c as (select * from {{ ref('stg_s4__customers') }})
select 'DQ01' as rule_id, 'Kunde ohne USt-IdNr.' as rule_text, 'KNA1' as object, customer as object_key,
       'mittel' as severity
from c where vat_id is null
union all
select 'DQ02', 'Mögliche Kundendublette (gleicher Name und Ort)', 'KNA1', c1.customer, 'hoch'
from c c1 join c c2 on c1.customer_name = c2.customer_name and c1.city = c2.city and c1.customer > c2.customer
union all
select 'DQ03', 'Kunde ohne Vertriebsdaten (keine Kundengruppe)', 'KNVV', customer, 'mittel'
from c where sales_org is null
union all
select 'DQ04', 'Buchung auf Kostenstelle außerhalb der Gültigkeit', 'ACDOCA',
       company_code || '/' || fiscal_year || '/' || document_number, 'hoch'
from {{ ref('fct_journal_line') }} where cost_centre is not null and cost_centre_sk is null
union all
select 'DQ05', 'Kostenstelle ohne Verantwortlichen', 'CSKS', cost_centre, 'mittel'
from {{ ref('stg_s4__cost_centres') }} where responsible is null or responsible = ''
union all
select 'DQ06', 'Verkauftes Material ohne Standardpreis im Geschäftsjahr', 'MBEW', s.material || '/' || s.fiscal_year, 'hoch'
from (select distinct material, fiscal_year from {{ ref('fct_sales_item') }} where material_group <> 'PG50') s
left join {{ ref('stg_s4__standard_prices') }} p on p.material = s.material and p.fiscal_year = s.fiscal_year
where p.material is null
