-- Open receivables and payables at the as-of date (input of the 13-week liquidity forecast)
select
    company_code, fiscal_year, document_number, line_item, gl_account,
    case gl_account when '120000' then 'AR' else 'AP' end as item_type,
    customer, vendor, posting_date, due_date, amount_lc, amount_eur
from {{ ref('stg_s4__journal_lines') }}
where gl_account in ('120000', '330000')
  and clearing_document is null
  and posting_date <= cast('{{ var("as_of_date") }}' as date)
