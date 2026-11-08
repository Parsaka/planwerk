select
    m.material, m.material_text, m.material_type, m.material_group,
    case m.material_group when 'PG10' then 'Kreiselpumpen' when 'PG20' then 'Dosierpumpen'
         when 'PG30' then 'Ventile und Armaturen' when 'PG40' then 'Ersatzteile' when 'PG50' then 'Service'
         when 'STAHL' then 'Guss- und Stahlteile' when 'KUNST' then 'Dichtungen und Kunststoffteile'
         when 'ELEK' then 'Motoren und Elektronik' end as material_group_text,
    m.base_unit
from {{ ref('stg_s4__materials') }} m
