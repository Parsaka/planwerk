# ADR-0001: Business questions, hypotheses and success criteria

- **Status:** Accepted (pre-registered before any analysis was run)
- **Date:** 2026-11-07
- **Deciders:** Parsa Kamali (project lead), steering committee (simulated)

## Context

Planwerk is a controlling and planning platform on SAP S/4HANA-shaped data with an AI
controlling assistant. Without fixed questions, a platform like this turns into a
dashboard collection. This ADR fixes three business questions, the hypothesis behind
each, the exact metric, and the threshold that counts as "answered". Everything later
(data model, marts, forecast, assistant, evaluation) exists to answer these three.

The data is **simulated** ("Nordwerk GmbH", Track B, see [ADR-0002](0002-simulated-data-track-b.md)).
The generator injects known effects and writes them to a ground-truth manifest, so the
analysis can be tested against the truth, which real data never allows. Real macro drivers
(Eurostat/Destatis producer prices, Eurostat labour cost index, ECB FX, SMARD power prices)
shape the cost side.

The questions are fixed **before** results exist. If a result turns out negative, it is
reported as negative. Thresholds are not moved after the fact.

## Q1: Where does the contribution-margin gap against plan come from?

> *Wie setzt sich die Plan-Ist-Abweichung im Deckungsbeitrag zusammen (Preis, Menge, Mix,
> Kosten), und welcher Anteil entfällt auf welche Kostenstelle?*

**Hypothesis H1.** The fiscal-year 2025 gap in DB II (Ist vs. Plan) can be split without
residual into price, volume, mix and cost effects per product group and company code, and
the cost part can be traced to cost centres such that at least 90 % of the cost deviation
is assigned to named cost centres (not "Sonstige").

**Method.** Price-volume-mix decomposition (PVM) on DB I (revenue minus variable cost of goods sold at standard), cost variance per cost element
and cost centre on DB II, following the standard controlling convention:

| Effect | Formula (per product group *g*) |
|---|---|
| Volume | (Q_ist,total − Q_plan,total) × plan mix share_g × plan unit margin_g |
| Mix | Q_ist,total × (mix share_ist,g − mix share_plan,g) × plan unit margin_g |
| Price | Q_ist,g × (P_ist,g − P_plan,g) |
| Cost (variable) | Q_ist,g × (c_plan,g − c_ist,g) |
| Fixed cost | Σ cost centre (Plan − Ist) for fixed cost elements |
| Currency | DB at actual FX rate − DB at plan FX rate (company code 3000, PLN) |

All effects are signed so that a positive value improves DB (favourable). Price, volume,
mix and variable cost are computed at plan FX rates (constant currency); the currency
effect is shown separately.

**Success criteria.**
1. Decomposition closes: |sum of effects − total gap| < 0.01 EUR (accounting identity, unit-tested).
2. Recovery: on simulated data, each injected effect (ground-truth manifest) is recovered
   within ±10 % of its injected size, or ±50 k EUR, whichever is larger.
3. Cost-centre coverage: ≥ 90 % of the absolute cost deviation is assigned to named cost centres.

## Q2: How many months earlier does a rolling ML forecast flag a missed annual target?

> *Wie viele Monate früher erkennt ein rollierender ML-Forecast eine Zielverfehlung im
> Jahresergebnis als eine lineare Hochrechnung?*

**Hypothesis H2.** A rolling forecast that uses order intake (VBAK) as a leading indicator
and seasonality detects a missed annual DB II target at least **2 months earlier** (median)
than straight-line extrapolation (YTD × 12 / m), with a false-alarm rate no higher than
the straight-line method.

**Definitions (fixed).**
- *Target:* Plan DB II for the fiscal year (version PLN).
- *Miss:* actual annual DB II < 98 % of target.
- *Flag at month m:* the method's full-year forecast made with data up to month m is
  < 98 % of target.
- *Detection month:* the first month m from which the flag stays on for every later month
  (a stable signal, not a single blip).
- *Lead time advantage:* detection month (straight-line) − detection month (ML). Undetected
  by month 12 counts as month 13.
- *False alarm:* a scenario without a miss in which a method has a stable flag at any month ≤ 11.

**Method.** Backtest over ≥ 200 simulated scenarios (different seeds and effect sizes, about
half of them with a true miss) plus the main 2025 scenario. Methods compared:
(a) straight-line extrapolation, (b) seasonal naive (prior-year shape), (c) ML
(gradient-boosted regression on order intake lags, seasonality and driver indices),
trained only on data before the forecast month (no leakage, checked by test).

**Success criteria.** Median lead time advantage of (c) over (a) ≥ 2 months **and**
false-alarm rate (c) ≤ false-alarm rate (a). Results are reported with interquartile range.

## Q3: Can AI write German month-end commentary with 100 % correct figures?

> *Kann eine KI den monatlichen Controlling-Kommentar auf Deutsch so schreiben, dass alle
> Zahlen korrekt sind und der Controller mindestens 50 % Zeit spart?*

**Hypothesis H3.** With a fact-first architecture (figures computed by SQL on semantic
views, the language model only phrases them, a verifier checks every number in the text
against the fact sheet), the assistant produces month-end commentary in which 100 % of the
figures are correct on a fixed test set, and reduces the controller's writing time by ≥ 50 %.

**Fixed test set.** 36 commentaries: 12 months of 2025 × 3 company codes (1000, 2000, 3000),
plus the consolidated view for Q4. Frozen in `eval/commentary_testset.yaml`.

**Success criteria.**
1. *Figure correctness:* 100 % of numeric tokens in every commentary match a fact-sheet value
   after German number parsing (tolerance: displayed rounding). Any single wrong figure fails
   the commentary. Measured automatically in CI.
2. *Q&A accuracy:* ≥ 95 % on the 200-question golden set (`eval/golden_set.yaml`), where each
   expected answer is computed by SQL, not written by hand.
3. *Time saving:* ≥ 50 % median reduction in writing time versus manual writing, measured by
   a timed protocol with at least one practising controller (see `docs/fachlich/zeitmessung.md`).
   On simulated data without a real controller, this criterion stays **open** and is
   reported as open, not as met.
4. *Safety:* 0 successful prompt-injection or write-SQL attempts in the guardrail test suite.

## Consequences

- The data model must carry plan quantities and prices (not only amounts) so that PVM works.
- The generator must produce order intake ahead of billing, so that a leading indicator exists.
- The assistant must never compute figures in the language model; it calls tools.
- Every result page in the documentation states whether a criterion was met, missed or is open.
