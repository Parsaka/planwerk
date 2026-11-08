-- Universal Journal at line grain, with the cost-centre version valid on the posting date
select
    j.*,
    cc.cost_centre_sk
from {{ ref('stg_s4__journal_lines') }} j
left join {{ ref('dim_cost_centre') }} cc
  on cc.cost_centre = j.cost_centre
 and j.posting_date between cc.valid_from and cc.valid_to
