select prctr as profit_centre, bukrs as company_code, ktext as profit_centre_name
from {{ source('s4', 'cepc') }}
