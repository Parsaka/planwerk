-- Revenue of the costed sales items equals revenue on the G/L per company code and period
with a as (select company_code, period, sum(revenue_lc) r from {{ ref('fct_sales_item') }} group by all),
     g as (select company_code, period, -sum(amount_lc) r from {{ ref('stg_s4__journal_lines') }}
           where gl_account in ('400000', '405000') group by all)
select * from a full outer join g using (company_code, period)
where abs(coalesce(a.r, 0) - coalesce(g.r, 0)) > 0.01
