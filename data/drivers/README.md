# Macro drivers (real data)

These files are the only real data in Planwerk. They shape the cost and currency side of the
simulated Nordwerk group. Snapshot taken on 2026-11-07; refresh with `python -m planwerk.drivers_fetch`.

| File | Source | Series | Unit |
|---|---|---|---|
| `eurostat_ppi_de_monthly.csv` | Eurostat `sts_inpp_m` (national data supplied by Destatis) | Producer prices in industry, Germany, NSA: total industry (B-E36), basic metals (C24), rubber and plastics (C22), machinery (C28), energy supply (D35), intermediate goods (MIG_ING) | Index 2021 = 100 |
| `eurostat_labour_cost_index_quarterly.csv` | Eurostat `lc_lci_r2_q` | Labour cost index, manufacturing (NACE C), wages and salaries plus employer costs (D1_D4_MD5), seasonally and calendar adjusted (SCA), DE / AT / PL | Index 2020 = 100 |
| `ecb_eur_pln_monthly.csv` | ECB Data Portal `EXR.M.PLN.EUR.SP00.A` | EUR/PLN reference rate, monthly average | PLN per EUR |
| `smard_dayahead_de_lu_monthly.csv` | SMARD (Bundesnetzagentur), filter 4169 | Day-ahead wholesale price, bidding zone DE-LU, monthly | EUR/MWh |

How the generator uses them:

- Component purchase prices follow C24 (cast/steel parts), C22 (seals/plastics) and C28 (motors/electronics, proxy).
- Personnel cost per head follows the labour cost index of the company code's country.
- 30 % of electricity is bought at the SMARD spot price, 70 % is hedged at a fixed price signed the autumn before (plus grid fees and levies). SMARD DE-LU is used as a proxy for AT and PL.
- Polish revenue and costs are translated to EUR at the ECB monthly average.

Licences: Eurostat and ECB data may be reused with attribution; SMARD data is published under CC BY 4.0 (Bundesnetzagentur | SMARD.de).
