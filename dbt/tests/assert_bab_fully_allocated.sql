-- After the BAB no cost is left on a service cost centre
select * from {{ ref('mart_db_statement_monthly') }}
where abs(fix_unallocated_eur) > 0.01 or abs(fix_unallocated_cc_eur) > 0.01
