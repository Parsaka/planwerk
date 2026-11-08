select
    p.vbeln                as sales_order,
    p.posnr                as sales_order_item,
    h.erdat                as order_date,
    {{ period_of('h.erdat') }} as order_period,
    h.vkorg                as company_code,
    h.kunnr                as customer,
    h.kdgrp                as customer_group,
    h.waerk                as currency,
    p.matnr                as material,
    p.matkl                as material_group,
    p.kwmeng               as quantity,
    p.netpr                as net_price,
    p.netwr                as net_value,
    p.edatu                as delivery_date
from {{ source('s4', 'vbap') }} p
join {{ source('s4', 'vbak') }} h on h.vbeln = p.vbeln
