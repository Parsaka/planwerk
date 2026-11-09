# ADR-0004: Fact-first AI assistant (the model never computes figures)

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

Language models make arithmetic and recall errors. A controlling commentary with a single
wrong number is worse than none: the CFO stops trusting the tool. Q3 (ADR-0001) demands 100 %
correct figures.

## Decision

1. Figures come only from **read-only SQL on semantic views** (`semantic.*`). SQL is generated
   from a whitelist of intents with parameters, or, for free questions, validated with
   `sqlglot` (SELECT only, allowed views only, row limit) before execution.
2. The model receives a **fact sheet** (ids, values, units) and must reference every number by
   fact id. The renderer replaces ids with German-formatted values.
3. A **verifier** parses every number in the final text (German format: 1.234,5; 3,2 %;
   1,2 Mio. EUR) and checks it against the fact sheet. Unverified numbers block the answer.
4. The orchestration is a small **LangGraph** state machine: classify -> plan query ->
   validate -> execute -> draft -> verify -> (retry once | answer).
5. The LLM provider is pluggable (Azure OpenAI per the target architecture; an offline
   deterministic writer for CI and for runs without credentials).

## Consequences

- CI can test the whole pipeline without an API key; the model-quality part of the eval runs
  when `AZURE_OPENAI_*` secrets are present.
- Commentary style is limited by the fact sheet: the model can explain, not invent.

## Amendment 2026-11-09: the verifier compares notation, not values

Decision 3 originally compared values: a number passed if some fact lay within the rounding
tolerance of what was written, and the parser knew only the house units (`Mio. EUR`, `TEUR`,
`EUR`, `%`). Two gaps followed.

- A figure in another notation was not recognised as a figure. "25 Millionen Euro" was read as
  the bare integer 25, and bare integers up to 31 pass as day or month numbers.
- A coarsely rounded figure has a wide tolerance. "EUR 7 Mio." matches any fact between 6.5 and
  7.5 M EUR, and a fact sheet with thirty facts usually has one.

The original hostile test model wrote its invented figure in house notation only, so the
evaluation did not see either gap. With a hostile model that rotates through eight notations the
old verifier delivered an invented figure in 34 of 39 commentaries and in 2 of 40 attacks
(`docs/ergebnisse/q3_eval_before_verifier_fix.json`).

Changed decision: the parser reads every spelling of magnitude, currency and percent; a figure
with a unit passes only if it is written exactly as the fact sheet renders one of its facts;
figures in words next to a unit are rejected. This is possible because numbers enter a text
only through placeholders that code fills in, so a correct text never needs another notation.

Remaining limit, by construction: a real figure under the wrong label passes, as does a bare
integer up to 31 or a year without a unit. Labels are fixed by the templates.

## Amendment 2026-11-10: rules route first, the model routes what the rules cannot place

The first evaluation with a real model (Azure OpenAI gpt-4o-mini,
`docs/ergebnisse/q3_eval_azure_first_run.json`) had the model route every question through function
calling. All 39 commentaries were correct in every figure and no attack succeeded, but only 91 of
200 golden-set questions were answered correctly: 50 routings failed validation or contradicted
the question, 35 chose the wrong evaluation, 24 the right evaluation with a wrong slot (15 of them
year to date for a single month).

Changed decision: `AzureOpenAIProvider.route` asks the deterministic rule-based parser first. The
model (`route_model`) is asked only when the parser returns no intent, and its answer passes the
same validation and consistency check as before. If the model cannot be reached after the client's
retries, such a question stays out of scope and the failure is counted in `usage.fallbacks`.

Consequences: fewer model calls per answer; the model's weakness in routing no longer reaches users
for questions the rules cover; the golden set stops measuring the model's routing (the holdout
through the full chain, `holdout_provider`, takes that role). Not yet measured with a real model.
