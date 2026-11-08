select matnr as material, cast(bdatj as integer) as fiscal_year, stprs as standard_price_eur
from {{ source('s4', 'mbew') }}
