-- Historic payment behaviour per customer: days between due date and payment (negative = early,
-- e.g. cash discount). Input of the 13-week liquidity forecast.
select
    company_code, customer,
    count(*) as paid_invoices,
    avg({{ dbt.datediff('due_date', 'clearing_date', 'day') }}) as avg_days_after_due,
    avg({{ dbt.datediff('posting_date', 'clearing_date', 'day') }}) as avg_days_to_pay
from {{ ref('stg_s4__journal_lines') }}
where gl_account = '120000' and document_type = 'RV' and clearing_document is not null
group by all
