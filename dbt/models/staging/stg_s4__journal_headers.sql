select bukrs as company_code, gjahr as fiscal_year, belnr as document_number, blart as document_type,
       budat as posting_date, bldat as document_date, usnam as created_by, waers as currency,
       nullif(xblnr, '') as reference, nullif(awtyp, '') as reference_type
from {{ source('s4', 'bkpf') }}
