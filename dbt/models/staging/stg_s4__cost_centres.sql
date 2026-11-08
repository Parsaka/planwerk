select
    kostl                  as cost_centre,
    bukrs                  as company_code,
    ltext                  as cost_centre_name,
    kosar                  as cost_centre_category,
    cm_level,
    verak                  as responsible,
    prctr                  as profit_centre,
    headcount              as headcount_reference,
    {{ to_date('datab') }} as valid_from,
    {{ to_date('datbi') }} as valid_to
from {{ source('s4', 'csks') }}
