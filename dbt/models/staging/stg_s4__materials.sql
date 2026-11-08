select
    matnr                  as material,
    maktx                  as material_text,
    mtart                  as material_type,
    matkl                  as material_group,
    meins                  as base_unit,
    list_price_2022,
    base_price             as purchase_base_price_eur,
    popularity
from {{ source('s4', 'mara') }}
