-- Gewinn- und Verlustrechnung nach § 275 Abs. 2 HGB (Gesamtkostenverfahren), actuals in EUR.
-- amount_eur is shown with income positive and expense negative.
select
    j.fiscal_year, j.period, j.company_code, a.gkv_position, g.text_de as gkv_text, g.sort,
    -sum(j.amount_eur) as amount_eur,
    -sum(j.amount_lc) as amount_lc
from {{ ref('stg_s4__journal_lines') }} j
join {{ ref('stg_s4__gl_accounts') }} a on a.gl_account = j.gl_account
join {{ ref('gkv_positions') }} g on g.gkv_position = a.gkv_position
where not a.is_balance_sheet
group by all
