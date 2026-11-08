select lifnr as vendor, name1 as vendor_name, land1 as country, bukrs as company_code,
       category as vendor_category, zterm as payment_terms
from {{ source('s4', 'lfa1') }}
