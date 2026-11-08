select kdgrp as customer_group, kbetr as discount_rate from {{ source('s4', 'discount_cond') }}
