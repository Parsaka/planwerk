-- One row per fiscal period (calendar months; fiscal year variant K4)
select
    period,
    cast(left(period, 4) as integer)  as fiscal_year,
    cast(right(period, 2) as integer) as fiscal_month,
    cast(period || '-01' as date)      as period_start,
    'Q' || cast((cast(right(period, 2) as integer) - 1) / 3 + 1 as varchar) as fiscal_quarter,
    case cast(right(period, 2) as integer)
        when 1 then 'Januar' when 2 then 'Februar' when 3 then 'März' when 4 then 'April'
        when 5 then 'Mai' when 6 then 'Juni' when 7 then 'Juli' when 8 then 'August'
        when 9 then 'September' when 10 then 'Oktober' when 11 then 'November' else 'Dezember'
    end as month_name_de
from {{ ref('stg_ext__drivers') }}
where period between '{{ var("first_period") }}' and '{{ var("last_period") }}'
