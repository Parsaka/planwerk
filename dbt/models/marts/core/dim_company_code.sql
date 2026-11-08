select company_code, company_name, country, local_currency, city, plant,
       true as is_simulated
from {{ ref('stg_s4__company_codes') }}
