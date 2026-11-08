select
    t.bukrs                as company_code,
    t.butxt                as company_name,
    t.land1                as country,
    t.waers                as local_currency,
    t.ort01                as city,
    w.werks                as plant
from {{ source('s4', 't001') }} t
left join {{ source('s4', 't001w') }} w on w.bukrs = t.bukrs
