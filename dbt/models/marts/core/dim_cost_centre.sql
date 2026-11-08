-- SCD type 2 cost-centre dimension from the CSKS validity intervals. A change of responsible
-- manager or profit-centre assignment creates a new version; facts join on posting date.
select
    {{ dbt_utils_surrogate(['cost_centre', 'valid_from']) }} as cost_centre_sk,
    cost_centre,
    company_code,
    cost_centre_name,
    cost_centre_category,
    cm_level,
    case cm_level when 'HILF' then 'Hilfskostenstelle'
                  when 'DB2' then 'Fertigung und Material'
                  when 'DB3' then 'Vertrieb, Service, Logistik'
                  else 'Verwaltung und Unternehmensleitung' end as cm_level_text,
    responsible,
    profit_centre,
    headcount_reference,
    valid_from,
    valid_to,
    valid_to = cast('9999-12-31' as date) as is_current
from {{ ref('stg_s4__cost_centres') }}
