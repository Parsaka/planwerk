select matnr as material, vkorg as sales_org, cast(left(datab, 4) as integer) as price_year,
       version as price_version, kbetr as list_price, konwa as currency
from {{ source('s4', 'price_list') }}
