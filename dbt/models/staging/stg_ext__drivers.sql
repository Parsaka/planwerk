select
    period,
    eur_pln,
    dayahead_eur_mwh,
    ppi_total_industry, ppi_basic_metals, ppi_rubber_plastics, ppi_machinery, ppi_energy_d35,
    ppi_intermediate_goods, lci_de, lci_at, lci_pl
from {{ source('s4', 'drivers') }}
