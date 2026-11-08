# ADR-0002: Simulated S/4HANA data (Track B) with real macro drivers

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

The preferred path (Track A) is a real small German client with a DATEV/Lexware/SAP export.
No client is available at project start. SAP sample systems (e.g. the S/4HANA Fully-Activated
Appliance) need paid hosting and their data has no business story to analyse.

## Decision

Build on a seeded, tested generator for the fictional **Nordwerk GmbH** (pump and valve maker,
company codes DE/AT/PL, 36 months, 2023-01 to 2025-12) that writes S/4HANA table shapes
(ACDOCA, ACDOCP, BKPF/BSEG, CSKS, SKA1, MARA/MARC/MBEW, STPO, VBAK/VBAP, VBRK/VBRP, AFKO,
EKKO/EKPO, KNA1/KNVV, LFA1). Every table, report and page carries the label "simuliert".

The cost and currency side is driven by **real** public data: Eurostat/Destatis producer price
indices, the Eurostat labour cost index, ECB EUR/PLN and SMARD day-ahead power prices. That
makes the cost story credible (for example the 2025 rise in basic-metals prices is real).

The generator injects known business effects (price shortfall, lost customer, demand shift,
one-off repair) and writes them to `ground_truth.json`. The analysis is tested against this
ground truth, which real data never allows.

Track A stays open: outreach material is in `docs/outreach/`. The dbt staging layer is the
only place that would change for a real DATEV/SAP export.

## Consequences

- Results are statements about the method, not about a real company. This is said on every page.
- Data volume is a parameter: profile `ci` (5 %), `dev` (EUR 250 M revenue, ~2.4 M journal lines),
  `full` (15x, ~35 M lines).
- Same seed, same data (tested). Different seeds give the scenarios for the Q2 backtest.
