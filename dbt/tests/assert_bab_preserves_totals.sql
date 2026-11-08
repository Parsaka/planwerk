-- Allocation only moves cost between cost centres: total before = total after
select version, company_code, period
from {{ ref('mart_cost_centre_monthly') }}
group by all
having abs(sum(primary_lc) - sum(total_lc)) > 0.01
