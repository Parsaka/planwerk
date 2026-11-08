-- Every accounting document balances in transaction, local and group currency
select company_code, fiscal_year, document_number
from {{ ref('stg_s4__journal_lines') }}
group by all
having abs(sum(amount_tc)) > 0.005 or abs(sum(amount_lc)) > 0.005 or abs(sum(amount_eur)) > 0.005
