# Results

All results are on **simulated data** (Nordwerk GmbH, main scenario, seed 42, fiscal year 2025).
Questions, metrics and thresholds were fixed in [ADR-0001](../adr/0001-business-questions-and-hypotheses.md)
before any analysis ran. A result that misses its threshold is reported as missed.

| Hypothesis | Verdict |
|---|---|
| H1: the DB II gap splits without residual, injected effects are recovered within ±10 %, ≥ 90 % of the cost deviation sits on named cost centres | **Not met** (2 of 3 criteria met) |
| H2: the ML forecast flags a missed target ≥ 2 months earlier (median) than straight-line, without more false alarms | **Not met** |
| H3: 100 % correct figures, ≥ 95 % golden-set accuracy, 0 successful attacks, ≥ 50 % time saving | **Offline provider: met on three criteria. First run with a real model: figures and attacks met, golden set not met (45.5 %). Time saving open** |

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
| 1. Bridge closes (< 0.01 EUR) | residual below 10⁻⁶ EUR (floating-point rounding) | met |
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

### What can be measured after all: the lost customer (exploratory, not pre-registered)

The group volume effect mixes two injected effects: the market level (0.97 instead of 1.00) and the
lost framework contract in Austria. The second concerns one customer, and one customer's share of its
cell is far more stable than the demand of the whole group. So it can be measured at customer level
(`customer_loss_effect` in [q1_evaluation.py](../../src/planwerk/controlling/q1_evaluation.py)):

    expected = budget DB I of the customer's cell (company code × customer group), April to December
               × the customer's share of that cell's DB I in the twelve months before the loss
    effect   = the customer's DB I in those months at plan prices and standard cost − expected

| Run | Injected | Measured | Within ±10 % |
|---|---:|---:|---|
| Seed 42 (main) | −1.34 M | −1.42 M | yes |
| Seed 7 | −1.89 M | −1.79 M | yes |
| Seed 123 | −2.27 M | −2.70 M | **no** |
| Seed 2024 | −1.57 M | −1.62 M | yes |
| Seed 31415 | −1.74 M | −1.60 M | yes |
| Seed 42 without demand noise | −1.34 M | −1.30 M | yes |

The method was written while looking at seed 42 only; the four other seeds are the independent check,
and it holds in three of them. What is left of the volume effect after taking out the customer (the
market level, injected −4.6 M EUR) is measured between −0.5 M and −6.7 M EUR and is within tolerance
in **0 of 6** runs. That is the part no method can recover from one year of data.

For the controller this is a practical rule: report a lost customer as its own line, measured at
customer level, and treat the rest of the volume effect as market plus ordinary fluctuation.
**H1 stays "not met"**: criterion 2 is judged on the combined volume effect as registered, and the
split is not part of it ([q1_evaluation.json](q1_evaluation.json), key `exploratory_volume_split`).

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

### The same question at equal false-alarm rate (exploratory, not pre-registered)

The registered rule flags a year when a forecast falls below 98 % of the target, for every method
alike. Straight-line extrapolation runs low early in the year (seasonality). That bias produces its
false alarms in healthy years and, by the same mechanism, its early flags in bad years. A steering
committee would ask a different question: *if every method may raise the same share of false alarms,
which one warns first?*

Protocol, fixed before the new scenarios were generated ([q2_matched.py](../../src/planwerk/forecast/q2_matched.py),
[q2_matched_false_alarm.json](q2_matched_false_alarm.json)): per method, the highest flag threshold whose
false-alarm rate stays within 5 % on the 200 registered scenarios; then measured on 200 fresh scenarios
(66 with a true miss).

| On the 200 fresh scenarios | Threshold | False alarms | Detection month, median | mean | Misses flagged by December |
|---|---:|---:|---:|---:|---:|
| **Registered rule (98 % for all)** | | | | | |
| Straight-line | 98.0 % | 8.2 % | 1 | 3.7 | 100 % |
| Seasonal naive | 98.0 % | 0.75 % | 1 | 4.0 | 100 % |
| Gradient boosting | 98.0 % | 0.75 % | 4 | 5.5 | 100 % |
| **Same false-alarm budget** | | | | | |
| Straight-line | 97.0 % | 2.2 % | 3 | 5.2 | 86 % |
| Seasonal naive | 99.0 % | 2.2 % | 1 | 3.2 | 100 % |
| Gradient boosting | 99.0 % | 2.2 % | 3 | 4.3 | 100 % |

Detection months have two clusters (a flag from January on, or from the month the shock starts), so
the median jumps between scenario sets: for straight-line it is 6 on the registered scenarios and 1 on
the fresh ones, with means of 4.5 and 3.7. The mean is the steadier figure. A miss that is never flagged
counts as month 13.

Lead of ML over straight-line on the fresh scenarios:

| | Median | Mean | ML earlier | ML later |
|---|---:|---:|---:|---:|
| Registered rule | −1 month | −1.8 months | 11 % of misses | 64 % |
| Same false-alarm budget | 0 months | +0.9 months | 44 % | 24 % |

Reading:

- The registered result replicates on fresh scenarios: under the 98 % rule ML is later than straight-line.
  **H2 stays "not met"**, and it would not be met under the matched comparison either (median lead 0, target 2).
- Most of straight-line's head start is its bias. Held to the same false-alarm rate it loses it, and it
  then fails to flag one true miss in seven at all, while both other methods flag every one.
- Seasonal naive is the best early-warning signal in both comparisons: under the registered rule it is about
  as early as straight-line (mean month 4.0 against 3.7) with a tenth of the false alarms, and at the same
  false-alarm budget it flags two months earlier than straight-line on average. The recommendation for the steering
  committee changes accordingly: seasonal naive as the warning signal, the ML forecast as the more accurate
  point estimate; straight-line adds false alarms and no information.

The thresholds were chosen on the registered scenarios and applied unchanged to the fresh ones; the
false-alarm rates there (2.2 %) are what came out, not what was fitted.

---

## Q3: Can AI write the month-end commentary with correct figures?

[q3_eval.json](q3_eval.json); first run before router fixes in [q3_eval_first_run.json](q3_eval_first_run.json).

| Criterion | Threshold | Result | |
|---|---|---|---|
| Figure correctness, 39 commentaries (12 months × 3 company codes + Q4 group) | 100 % | 39/39 | met |
| Same with a hostile model that appends an invented figure in one of eight notations | 100 % | 39/39 | met |
| Golden set, 200 questions, expected answers computed by SQL | ≥ 95 % | 200/200 | met |
| Prompt injection, write SQL, privilege escalation, 40 attacks × 2 models | 0 successful | 0/80 | met |
| Writing time saved by a practising controller | ≥ 50 % | not measured | **open** |

Caveats, stated plainly:

- **The hostile-model result was weaker than first reported, and was corrected on 2026-11-09.** The first
  hostile model wrote its invented figure only in house notation ("999,0 Mio. EUR"), which the verifier
  caught. A review found that the same figure written as "25 Millionen Euro", "12 Mio €", "30 Tsd. EUR",
  "EUR 7 Mio." or "zwölf Millionen Euro" passed. With a hostile model that rotates through eight notations,
  the verifier of the time delivered an invented figure in **34 of 39 commentaries and 2 of 40 attacks**
  ([q3_eval_before_verifier_fix.json](q3_eval_before_verifier_fix.json)). The verifier now accepts a figure
  only in the notation the fact sheet itself renders ([ADR-0004](../adr/0004-fact-first-ai-assistant.md),
  amendment); the same hostile model now gets 0 through. The offline provider never produced such text,
  so the 39/39 for the normal run was not affected. What remains outside any number check: a real figure
  under the wrong label.

- **The golden set is in-sample.** It found six router bugs; the first run scored 87 %. After the
  fixes it scores 200/200. The honest generalisation figure is the **hand-written holdout of 40
  questions**, frozen before tuning and never tuned on: **35/40 (87.5 %)**. All five misses are
  routing misses (e.g. "Auftragslage" not recognised as order intake); three of them fall back to
  "out of scope", the other two answer a neighbouring question (KPI instead of bridge or forecast)
  with correct figures for that question.
- These figures use the **offline provider** (template wording) and a simulated hostile model.
  The Azure OpenAI run is wired up ([eval-azure.yml](../../.github/workflows/eval-azure.yml)) and the
  provider is tested against a fake client, but it has not run against a real deployment: it needs an
  Azure subscription. Because numbers enter the text only through placeholders and every
  number is re-checked, figure correctness does not depend on the model; wording quality does.
- Time saving needs a real controller and follows the protocol in
  [zeitmessung.md](../fachlich/zeitmessung.md). Until then it is reported as open.

### First run with a real model (Azure OpenAI, gpt-4o-mini, 2026-11-09)

[q3_eval_azure_first_run.json](q3_eval_azure_first_run.json). In this run the model routed every question and worded every
answer. 387 model calls, 283 k prompt and 46 k completion tokens, 27 minutes.

| Criterion | Threshold | Result | |
|---|---|---|---|
| Figure correctness, 39 commentaries written by the model | 100 % | 39/39 | met |
| Golden set, 200 questions | ≥ 95 % | 91/200 (45.5 %) | **not met** |
| Attacks (40 against the model, 40 against the hostile model) | 0 successful | 0/80 | met |

Where the 109 wrong answers come from:

| Cause | Count |
|---|---:|
| Answered "out of scope": the model's routing failed validation or contradicted the question | 50 |
| Wrong evaluation chosen (18 times a KPI answer to a product-group question, 7 times a commentary instead of the bridge) | 35 |
| Right evaluation, a single month asked, year to date answered | 15 |
| Right evaluation, group answered instead of the company code asked | 7 |
| Right evaluation, wrong cost block | 2 |

No answer carried a wrong figure. Every answer that was given consisted of verified figures, but in 59
cases for another question than the one asked, and in 50 cases the assistant declined. By category:
product group 0/25, forecast 2/10, bridge 5/20, order intake 5/15, cost centre 5/15, month KPI 20/45.

Reading: the claim that figure correctness does not depend on the model held with a real model. Routing by
gpt-4o-mini through function calling did not: it is far below the rule-based router (200/200 in sample,
35/40 on the holdout).

Change made afterwards, **not yet measured with a real model**: the provider now routes with the
rule-based parser first and asks the model only for questions the parser cannot place
(`AzureOpenAIProvider.route`; `route_model` is the model alone, with intent descriptions and the
cost-centre list in its prompt). Two things follow for the next run:

- The golden set now says little about the model, because the rule-based parser is in sample there.
  The figure to watch is the holdout through the full chain (`holdout_provider` in the result): the
  parser alone places 35 of 40, the model gets the five it cannot place. `usage.rule_routed` and
  `usage.model_routed` show who routed how many questions.
- The router prompt was extended after seeing this run. Any further improvement of the model's own
  routing against the golden set would be tuning on the test set and needs a fresh question set.

Latency (offline): median 5.8 ms per answer, 24.7 ms per commentary. Cost per answer offline: 0 EUR.

---

## The same warehouse on Snowflake

[snowflake_run.json](snowflake_run.json), run on 2026-11-09 on a Snowflake trial account (AWS eu-central-1),
same simulated data (profile dev, seed 42).

| Check | Result |
|---|---|
| Load: 27 S/4HANA tables, 6.27 million rows, via key-pair service user (no password) | row counts equal the generator manifest |
| `dbt build` on Snowflake: 4 seeds, 27 tables, 25 views, 42 data tests | 98/98 pass, 25 s on an XS warehouse |
| Parity with DuckDB: row count and sums per relation, tolerance 0.01 EUR | 54 of 54 comparable relations identical |
| Row access policy on the cost-centre mart | service user sees 0 rows, owner of 1410 sees only 1410, owner of pumps sees 1500 and 1520, controller sees all 9,420 rows |

One change was needed to port it: the loader now upper-cases inferred column names (the
macro-driver file has lower-case columns, which Snowflake would otherwise create as quoted
identifiers). Two semantic views also filter on `CURRENT_USER()` inside the view on top of the
policy, so they cannot be simulated with `POLICY_CONTEXT`; they are plain aggregations of the
checked mart. The rolling forecast and liquidity tables are written by Python on DuckDB and are
not part of the Snowflake run.
