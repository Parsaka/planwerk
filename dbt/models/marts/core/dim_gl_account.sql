select a.gl_account, a.gl_account_text, a.is_balance_sheet, a.gkv_position, g.text_de as gkv_text,
       g.sort as gkv_sort, a.cm_block
from {{ ref('stg_s4__gl_accounts') }} a
left join {{ ref('gkv_positions') }} g on g.gkv_position = a.gkv_position
