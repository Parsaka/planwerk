select p.*, a.cm_block, a.gkv_position
from {{ ref('stg_s4__plan_lines') }} p
join {{ ref('stg_s4__gl_accounts') }} a on a.gl_account = p.gl_account
