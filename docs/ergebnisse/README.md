# Results

All results are on **simulated data** (Nordwerk GmbH, main scenario, seed 42, fiscal year 2025).
Questions, metrics and thresholds were fixed in [ADR-0001](../adr/0001-business-questions-and-hypotheses.md)
before any analysis ran. A result that misses its threshold is reported as missed.

| Hypothesis | Verdict |
|---|---|
| H1: the DB II gap splits without residual, injected effects are recovered within ±10 %, ≥ 90 % of the cost deviation sits on named cost centres | **Not met** (2 of 3 criteria met) |
| H2: the ML forecast flags a missed target ≥ 2 months earlier (median) than straight-line, without more false alarms | **Not met** |
| H3: 100 % correct figures, ≥ 95 % golden-set accuracy, 0 successful attacks, ≥ 50 % time saving | **Met on three criteria, time saving open** |

Regenerate everything with `make all`. The raw numbers are in the JSON files next to this page.

---

## Q1: Where does the DB II gap come from?

Group DB II 2025: plan 98.42 M EUR, actual 93.93 M EUR, gap **−4.49 M EUR (−4.6 %)**.

| Effect | M EUR |
|---|---:|
| Volume | −1.93 |
| Mix | −0.71 |
| Price | −2.16 |
| Variable cost | +0.31 |
| Sales deductions | +0.02 |
| Fixed cost (to DB II) | −0.48 |
| Currency (PLN) | +0.46 |
| **Sum = gap** | **−4.49** |

| Criterion | Result | |
|---|---|---|
| 1. Bridge closes (< 0.01 EUR) | residual 1.2 × 10⁻⁷ EUR | met |
| 2. Each injected effect within ±10 % (min. ±50 k EUR) | 3 of 4 | **not met** |
| 3. ≥ 90 % of cost deviation on named cost centres | 100 % | met |

Recovery against the ground-truth manifest ([q1_evaluation.json](q1_evaluation.json)):

| Injected effect | Injected | Measured | Within tolerance |
|---|---:|---:|---|
| Price increase on centrifugal pumps 1.5 % instead of 4 % | −2.07 M | −2.15 M | yes |
| Demand shift from dosing to centrifugal pumps (mix) | −0.67 M | −0.71 M | yes |
| Market volume 0.97 + lost framework contract in Austria | −5.93 M | −1.93 M | **no** |
| One-off repair, cost centre 1410, June | −0.45 M | −0.45 M | yes |

### Why the volume effect is missed (exploratory, not pre-registered)

The injected effects are *expected* values. The generator then draws individual orders, quantities,
materials and customers, so a single year deviates from its expectation. In the main run, 2025
revenue came out **2.6 % above** its expected value, which adds about 4 M EUR of DB at plan prices
and hides most of the injected volume loss.

To check whether this is noise or a flaw in the method, the whole pipeline was re-run for four
more seeds and once with the demand noise switched off ([q1_robustness.json](q1_robustness.json),
`python -m planwerk.controlling.q1_robustness`):

| Effect | Recovered |
|---|---|
| Price (PG10) | 6 of 6 runs |
| One-off cost, cost centre 1410 | 6 of 6 runs |
| Mix | 1 of 6 runs |
| Volume | 0 of 6 runs |

The volume error is almost exactly a linear function of how far that year's revenue drifted from
its expectation: **+1.6 M EUR per +1 % of revenue, correlation 0.9999, intercept −0.11 M EUR**.
Removing the demand noise alone does not help (realisation still +2.5 %), because order counts,
quantities and material choice are still sampled.

Reading: the PVM decomposition is unbiased, but a ±10 % tolerance on volume and mix is tighter
than the year-to-year variation of a single realisation. In practice this is the normal case for
a controller as well: "volume" in a bridge is the injected market effect *plus* ordinary demand
fluctuation, and one year of data cannot separate them. Price and cost effects, which act on each
document, are recovered reliably. **The verdict on H1 stays "not met".** The criterion was not
loosened after the fact.

---

## Q2: Does the ML forecast warn earlier?

Backtest over 200 simulated scenarios, 67 of them with a true miss of the annual DB II target
(actual < 98 % of plan). [q2_backtest_summary.json](q2_backtest_summary.json), per scenario in
[q2_backtest_scenarios.csv](q2_backtest_scenarios.csv).

| Method | Median detection month | False-alarm rate | MAPE months 1–11 |
|---|---:|---:|---:|
| Straight-line (YTD × 12 / m) | 6 | 11.3 % | 4.3 % |
| Seasonal naive | 4 | 0.0 % | 4.1 % |
| Gradient boosting with order intake | 5 | 0.0 % | 3.8 % |

Lead of ML over straight-line: **median 0 months** (IQR −1 to 0), mean −0.84. Target was ≥ 2.
**H2 not met.**

What the backtest does show: the ML forecast is the most accurate of the three and has no false
alarms, while straight-line raises a false alarm in one of nine healthy years. Seasonal naive,
the simplest method, detects earliest. For the steering committee the recommendation is to report
straight-line and ML side by side and to escalate only when both agree. Order intake as a leading
indicator did not buy earlier warning in this simulation.

---

## Q3: Can AI write the month-end commentary with correct figures?

[q3_eval.json](q3_eval.json); first run before router fixes in [q3_eval_first_run.json](q3_eval_first_run.json).

| Criterion | Threshold | Result | |
|---|---|---|---|
| Figure correctness, 39 commentaries (12 months × 3 company codes + Q4 group) | 100 % | 39/39 | met |
| Same with a hostile model that invents numbers and swaps periods | 100 % | 39/39 | met |
| Golden set, 200 questions, expected answers computed by SQL | ≥ 95 % | 200/200 | met |
| Prompt injection, write SQL, privilege escalation, 40 attacks × 2 models | 0 successful | 0/80 | met |
| Writing time saved by a practising controller | ≥ 50 % | not measured | **open** |

Caveats, stated plainly:

- **The golden set is in-sample.** It found six router bugs; the first run scored 87 %. After the
  fixes it scores 200/200. The honest generalisation figure is the **hand-written holdout of 40
  questions**, frozen before tuning and never tuned on: **35/40 (87.5 %)**. All five misses are
  routing misses (e.g. "Auftragslage" not recognised as order intake); three of them fall back to
  "out of scope", the other two answer a neighbouring question (KPI instead of bridge or forecast)
  with correct figures for that question.
- These figures use the **offline provider** (template wording) and a simulated hostile model.
  The Azure OpenAI run is wired up ([eval-azure.yml](../../.github/workflows/eval-azure.yml)) but
  needs an Azure subscription. Because numbers enter the text only through placeholders and every
  number is re-checked, figure correctness does not depend on the model; wording quality does.
- Time saving needs a real controller and follows the protocol in
  [zeitmessung.md](../fachlich/zeitmessung.md). Until then it is reported as open.

Latency (offline): median 5.8 ms per answer, 24.7 ms per commentary. Cost per answer offline: 0 EUR.
