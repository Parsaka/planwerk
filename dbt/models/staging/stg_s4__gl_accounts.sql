select
    saknr                  as gl_account,
    txt50                  as gl_account_text,
    xbilk = 'X'            as is_balance_sheet,
    nullif(gkv_position, '') as gkv_position,
    nullif(cm_block, '')   as cm_block
from {{ source('s4', 'ska1') }}
