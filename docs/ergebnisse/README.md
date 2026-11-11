# Results

All results are on **simulated data** (Nordwerk GmbH, main scenario, seed 42, fiscal year 2025).
Questions, metrics and thresholds were fixed in [ADR-0001](../adr/0001-business-questions-and-hypotheses.md)
before any analysis ran. A result that misses its threshold is reported as missed.

| Hypothesis | Verdict |
|---|---|
| H1: the DB II gap splits without residual, injected effects are recovered within ±10 %, ≥ 90 % of the cost deviation sits on named cost centres | **Not met** (2 of 3 criteria met) |
| H2: the ML forecast flags a missed target ≥ 2 months earlier (median) than straight-line, without more false alarms | **Not met** |
| H3: 100 % correct figures, ≥ 95 % golden-set accuracy, 0 successful attacks, ≥ 50 % time saving | **Met on three criteria, time saving open** (offline and with Azure OpenAI gpt-4o-mini) |

Regenerate everything with `make all`. The same warehouse also runs on Snowflake ([below](#the-same-warehouse-on-snowflake)). The raw numbers are in the JSON files next to this page.

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
- The table above uses the **offline provider** (template wording) and a simulated hostile model.
  The real-model run is below.
- Time saving needs a real controller and follows the protocol in
  [zeitmessung.md](../fachlich/zeitmessung.md). Until then it is reported as open.

Latency (offline): median 5.8 ms per answer, 24.7 ms per commentary. Cost per answer offline: 0 EUR.

### With the real model: Azure OpenAI gpt-4o-mini

[q3_eval_azure.json](q3_eval_azure.json), run in GitHub Actions on 2026-11-09 against
gpt-4o-mini (2024-07-18, Data Zone EU, Sweden Central), signed in through OIDC with no API key.

| Criterion | Threshold | First run | Final run | |
|---|---|---|---|---|
| Figure correctness, 39 commentaries | 100 % | 39/39 | 39/39 | met |
| Same with the hostile model | 100 % | 39/39 | 39/39 | met |
| Golden set, 200 questions | ≥ 95 % | 91/200 (45.5 %) | 199/200 (99.5 %) | met |
| Prompt injection, 40 attacks × 2 models | 0 successful | 0/80 | 0/80 | met |
| Holdout, 40 paraphrases, full routing chain | reported, no threshold | – | 36/40 (parser alone 35/40) | |

The **first run failed** ([q3_eval_azure_first_run.json](q3_eval_azure_first_run.json)). The model
did the routing alone: it sent 49 recognisable questions out of scope and read "April 2025" as
"January to April". The fix is architectural, not a prompt tweak. The rule-based parser now
routes every question it recognises (235 of 253 in the final run). The model only routes what the
parser leaves out of scope (18), and its intent still has to pass the closed-vocabulary
validation and the consistency check. The one remaining golden-set miss (g095) is a rewrite that
dropped plan and actual from a bridge answer. The verifier only blocks invented numbers, so the
answer went out without them.

The golden set is still in-sample for the parser, so 199/200 mostly measures the parser plus the
model's wording. The honest figure is the holdout through the full chain: **36/40**. The model
fixed two paraphrases the parser missed and broke one the parser had right.

The later run with document search (below) scored 200/200 on the golden set and 36/40 on the holdout.

Latency with the model: median 3.0 s per answer (p95 6.6 s), 12 s per commentary. Cost: about
0.003 EUR per answer, 0.95 EUR for the whole run (list-price estimate).

### Method and governance questions from the documents (RAG)

The assistant also answers questions like "Wie wird der Mixeffekt berechnet?" or "Wer darf alle
Kostenstellen sehen?" from the German project documents (Fachkonzept, Lastenheft, governance,
runbook), always naming the source section. A number may appear in such an answer only if it is in
the retrieved passages. Whether a question is in scope is decided locally, never by the model or
the search service. There is no pre-registered threshold for this; the figures are supplementary.

[method_questions.yaml](../../eval/method_questions.yaml): 32 questions plus 10 off-topic ones,
written before the first run.

| Run | Search | Answered | Expected source in top 3 | Off-topic refused |
|---|---|---|---|---|
| First run, offline ([rag_first_run.json](rag_first_run.json)) | BM25, local | 26/32 | 23/32 | 9/10 |
| After two general fixes, offline (in-sample) | BM25, local | 29/32 | 25/32 | 10/10 |
| Same, with gpt-4o-mini ([q3_eval_azure.json](q3_eval_azure.json)) | Azure AI Search (free tier, Entra ID only) | 25/32 | 24/32 | 10/10 |

The fixes: the question-phrasing verbs ("berechnet", "gilt", "sehen") no longer count as evidence,
and German compounds are split ("Währungseffekt" → "Währung" + "Effekt"). With the model, all 25
answers name the expected term. Four times the passages did not contain the answer and the model
said so instead of guessing; those count as misses. "Wer darf alle Kostenstellen sehen?" is refused
in every run: the gate does not recognise it as in scope.

The run with search also kept the golden set at 200/200 and 0/80 successful attacks. Cost of the
whole run: 1.03 EUR.

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

---

## The CAP service on SAP BTP with HANA Cloud

[btp_run.json](btp_run.json), deployed on 2026-11-10 to an SAP BTP trial (Cloud Foundry, US East)
with SAP HANA Cloud (free plan), an HDI container and XSUAA, from [sap/cap](../../sap/cap).

| Check ([btp-smoke.js](../../sap/cap/scripts/btp-smoke.js)) | Result |
|---|---|
| Request without a token | 401 |
| Group DB II, December 2025, read through OData from HANA | identical to the warehouse to the cent |
| KPI rows in HANA vs exported data | 1,440 of 1,440 |
| DB II bridge closes (function on HANA) | rest 0.01 EUR, within the 0.07 EUR rounding tolerance |
| Largest unfavourable cost-centre deviation | 1410, the injected one-off repair |
| Write attempt (POST) | 403, the service is read-only |

The first deploy failed: HANA rejected "unternehmensfixkosten" (21 characters) in a String(20)
column, which SQLite in the unit tests had accepted. The column is now String(40), and a new test
checks every initial-data value against its column length.

The live test uses the app's own technical client, which holds only the Controller scope. The
cost-centre owner restriction was not tested with a real BTP user, because that needs a role
collection with the `kostenstelle` attribute assigned to a person. It is covered by the local CAP
tests and was verified on Snowflake. The trial HANA instance stops every night and has to be
restarted before use.

---

## SAP Analytics Cloud and SAP Datasphere

[sap_trials_run.json](sap_trials_run.json), built on 2026-11-11 in an SAC trial (2026 Q4 QRC,
Planning Professional) and the SAP Datasphere basic trial, through the browser. The import files come
from `python -m planwerk.sac.export` on the same warehouse. Screenshots are in [sap/](sap/).

| Check | Expected (warehouse) | Seen | |
|---|---|---|---|
| SAC NW_CONTROLLING rows imported | 21,000 | 21,000 | ✓ |
| SAC Actual 2025 product revenue (ERL_PROD) | 262,711,023.29 | 262,711,023.29 | ✓ |
| SAC Actual 2025 variable cost (VAR_MAT) | 101,544,394.96 | 101,544,394.96 | ✓ |
| SAC Actual 2025 fixed-cost accounts | 109,230,581.31 | 109,230,581.31 | ✓ |
| SAC Actual 2025 cash discount (ERL_SKONTO) | 1,708,511.98 | 1,708,511.99 | 1 cent, see below |
| SAC data action DA_01 (Actual Jan–Jun 2025 into FC6_6_2025) | 1,770 rows, 234,991,696.03 | 1,770 rows, 234,991,696.03 | ✓ |
| Datasphere DB I Actual 2025 (view V_DB_STATEMENT, analytic model AM_DB_STATEMENT) | 159,458,116.35 | 159,458,116.34 | 1 cent, see below |

The two one-cent gaps are float rounding in the reference figures, which were summed from the CSV
in Python; SAC and Datasphere sum the same CSV rows to the values shown. The story
"Monatsbericht Nordwerk (simuliert)" shows Actual vs Budget 2025 per company with cost-centre,
date and version filters and a button for DA_01.

What did not work, kept as found:

- **The DA_01 script in the spec was wrong.** SAC refused `DATA([d/Version] = ...)` with
  "The version dimension cannot be used in the left operand". The target version is now chosen when
  the data action runs; [sac/README.md](../../sac/README.md) is corrected.
- **DA_02 (driver-based budget 2026 via LINK) was not saved.** SAC asks for "ProductGroup, Entity,
  Version" to be specified for NW_SALES_DRIVERS, because both models use their own private
  dimensions. It needs shared public dimensions or an explicit mapping in LINK.
- **No hierarchies in SAC.** Account, Entity, ProductGroup and CostCenter were imported flat, so the
  story cannot roll up DB I to BE as a hierarchy yet.
- **No data access control in Datasphere.** The DB view aggregates the cost centre away; a DAC needs
  a user-to-cost-centre table and a fact view at cost-centre level. Cost-centre restriction is shown on
  Snowflake and in CAP instead.
- The Datasphere basic trial is a shared SAP tenant with one personal space, not a full tenant.

