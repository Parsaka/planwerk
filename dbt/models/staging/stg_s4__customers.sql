select
    k.kunnr                as customer,
    k.name1                as customer_name,
    k.land1                as country,
    k.ort01                as city,
    nullif(k.stceg, '')    as vat_id,
    v.vkorg                as sales_org,
    v.kdgrp                as customer_group,
    v.zterm                as payment_terms
from {{ source('s4', 'kna1') }} k
left join {{ source('s4', 'knvv') }} v on v.kunnr = k.kunnr
