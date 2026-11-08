select
    customer, customer_name, country, city, sales_org as company_code, customer_group,
    case customer_group when '01' then 'OEM / Anlagenbauer' when '02' then 'Industrie'
         when '03' then 'Kommunal / Wasserwirtschaft' when '04' then 'Handel' end as customer_group_text,
    payment_terms, vat_id
from {{ ref('stg_s4__customers') }}
where sales_org is not null
