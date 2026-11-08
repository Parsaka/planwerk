select
    p.vbeln                as billing_document,
    p.posnr                as billing_item,
    h.fkdat                as billing_date,
    {{ period_of('h.fkdat') }} as period,
    h.bukrs                as company_code,
    h.kunrg                as customer,
    h.waerk                as currency,
    h.zterm                as payment_terms,
    p.aubel                as sales_order,
    p.aupos                as sales_order_item,
    p.matnr                as material,
    p.matkl                as material_group,
    p.fkimg                as quantity,
    p.netwr                as net_value,
    p.prctr                as profit_centre
from {{ source('s4', 'vbrp') }} p
join {{ source('s4', 'vbrk') }} h on h.vbeln = p.vbeln
