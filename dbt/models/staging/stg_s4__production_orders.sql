select aufnr as production_order, matnr as material, gamng as quantity, werks as plant,
       bukrs as company_code, kostl as cost_centre, gltri as finish_date,
       kdauf as sales_order, kdpos as sales_order_item
from {{ source('s4', 'afko') }}
