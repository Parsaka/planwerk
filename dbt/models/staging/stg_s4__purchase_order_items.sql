select h.ebeln as purchase_order, p.ebelp as purchase_order_item, h.bukrs as company_code,
       h.lifnr as vendor, h.bedat as order_date, p.matnr as material, p.menge as quantity,
       p.netpr as net_price_eur, p.netwr as net_value_eur
from {{ source('s4', 'ekpo') }} p
join {{ source('s4', 'ekko') }} h on h.ebeln = p.ebeln
