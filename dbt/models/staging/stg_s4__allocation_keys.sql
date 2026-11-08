select bukrs as company_code, kostl as cost_centre,
       key_energy, key_maint as key_maintenance, key_it
from {{ source('s4', 'alloc_keys') }}
