select
    category               as plan_category,
    rbukrs                 as company_code,
    cast(ryear as integer) as fiscal_year,
    {{ period_from_parts('ryear', 'poper') }} as period,
    racct                  as gl_account,
    nullif(rcntr, '')      as cost_centre,
    nullif(prctr, '')      as profit_centre,
    nullif(matkl_mm, '')   as material_group,
    nullif(kdgrp, '')      as customer_group,
    hsl                    as amount_lc,
    ksl                    as amount_eur,
    msl                    as quantity,
    plan_fx_eur_pln
from {{ source('s4', 'acdocp') }}
