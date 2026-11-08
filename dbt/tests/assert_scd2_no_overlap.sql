-- SCD2 versions of a cost centre never overlap
select a.cost_centre
from {{ ref('dim_cost_centre') }} a
join {{ ref('dim_cost_centre') }} b
  on a.cost_centre = b.cost_centre and a.cost_centre_sk <> b.cost_centre_sk
 and a.valid_from <= b.valid_to and b.valid_from <= a.valid_to
