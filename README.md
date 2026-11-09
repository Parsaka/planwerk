# Planwerk

**Controlling and planning platform on SAP S/4HANA-shaped data, with an AI controlling assistant
whose figures are checked one by one.**

[Deutsche Fassung](README.de.md) · [Results](docs/ergebnisse/README.md) · [ADR-0001: questions and hypotheses](docs/adr/0001-business-questions-and-hypotheses.md)

> **All company data is simulated.** Nordwerk GmbH is a fictional pump manufacturer with three
> company codes (DE, AT, PL). The generator is open, seeded and tested. Only the macro drivers are
> real: Eurostat/Destatis producer prices and labour costs, ECB exchange rates, SMARD power prices.

## Why it exists

Planwerk answers three questions that were fixed, with thresholds, before any analysis ran:

| | Question | Result |
|---|---|---|
| Q1 | Where does the 4.5 M EUR gap in contribution margin II against plan come from (price, volume, mix, cost; which cost centre)? | Bridge closes to the cent, 100 % of the cost deviation sits on named cost centres. Of four injected effects, three are recovered within tolerance; the volume effect is not, because one year's demand fluctuation swamps it (shown over six runs). **H1 not met.** |
| Q2 | How many months earlier does a rolling ML forecast flag a missed annual target than straight-line extrapolation? | Over 200 simulated scenarios the median lead is 0 months (target: 2). ML has no false alarms against 11.3 % for straight-line. **H2 not met.** |
| Q3 | Can AI write the German month-end commentary with 100 % correct figures and save half the controller's time? | Offline (rule-based routing, template wording): 39/39 commentaries with every figure correct, also with a deliberately hostile model; 200/200 golden-set questions; 0 of 80 injection attempts succeeded. First run with Azure OpenAI gpt-4o-mini: again 39/39 and no successful attack, but only 91/200 golden-set questions, because the model routed questions badly; routing now uses the rules first (not yet re-measured). Time saving needs a practising controller: **open.** |

Negative results are reported as negative; thresholds were not moved. Details, caveats and
the multi-seed robustness check are on the [results page](docs/ergebnisse/README.md).

## What is in the repository

```
SAP S/4HANA-shaped tables (ACDOCA, ACDOCP, BKPF/BSEG, VBAK/VBAP/VBRK/VBRP, EKKO/EKPO, AFKO, MARA/MARC/MBEW, KNA1, LFA1, CSKS ...)
        │  src/planwerk/generator   seeded simulation, real macro drivers, ground-truth manifest
        ▼
dbt (DuckDB locally, Snowflake-portable)
        staging → intermediate (BAB allocation, costed sales items) → core (Kimball, SCD2 cost centres)
        → controlling marts (DB I–III, PVM bridge, cost variance, HGB GKV P&L, order intake)
        → semantic views with row-level security per cost-centre owner
        │
        ├── forecast/       rolling 3+9 / 6+6 / 9+3, straight-line vs seasonal-naive vs gradient boosting, Q2 backtest
        ├── controlling/    13-week liquidity forecast, Q1 evaluation against the ground truth
        ├── reporting/      German Excel month-end report (XVERWEIS, tables, Power Query notes), steering-committee deck
        ├── sac/            SAC Planning import files and model design (driver-based plan 2026, data actions)
        └── assistant/      fact-first assistant: intents → read-only SQL → fact sheet → wording → number verifier
                            LangGraph flow, Azure OpenAI or offline provider, MCP server, guardrails, audit log
```

| Area | Where |
|---|---|
| Business documents (German) | [Lastenheft](docs/fachlich/lastenheft.md), [Fachkonzept](docs/fachlich/fachkonzept.md), [Zeitmessung](docs/fachlich/zeitmessung.md) |
| Decisions | [docs/adr](docs/adr) |
| Governance (German) | [Berechtigungskonzept](docs/governance/berechtigungskonzept.md), [VVT](docs/governance/vvt.md), [DSFA](docs/governance/dsfa.md), [EU AI Act](docs/governance/eu-ai-act.md), [Kontrollmatrix](docs/governance/kontrollmatrix.md), [Audit-Log](docs/governance/audit-log.md) |
| Operations | [Runbook](docs/betrieb/runbook.md), [Definition of Done](docs/projekt/definition-of-done.md) |
| Data contract | [contracts/s4_sources.yaml](contracts/s4_sources.yaml) (27 tables, types, keys) |
| Infrastructure | [infra/terraform](infra/terraform): Snowflake (roles, service users, resource monitor) and Azure (OpenAI with Entra ID only, Key Vault, budget, GitHub OIDC) |
| AI evaluation | [eval](eval): 200-question golden set, 40 hand-written holdout questions, 40 injection attacks, 39 commentary cases |
| Track A outreach (German) | [docs/outreach](docs/outreach) |

## Run it

Everything runs locally on DuckDB, without cloud accounts. Python 3.11+.

```bash
make install            # pip install -e ".[dbt,assistant,reporting,dev]"
make generate           # ~45 s, ~2.4 M journal lines (dev profile, seed 42)
make dbt                # build and test the warehouse
make forecast backtest liquidity q1
make eval               # Q3: golden set, holdout, injection suite, commentary
make reports            # reports/out/Monatsbericht_Nordwerk_2025-12.xlsx and Lenkungskreis_Nordwerk_GJ2025.pptx
make test lint
```

Ask the assistant:

```bash
make assistant Q="Warum liegt der DB II 2025 unter Plan?"
PLANWERK_LLM=azure make assistant Q="..."   # Azure OpenAI, needs the variables in the runbook
planwerk-mcp                                 # MCP server (stdio) with read-only tools
```

## How the assistant keeps figures correct

1. The question is mapped to one of a closed set of intents and checked against what the user
   actually asked (year, month, company code, cost centre).
2. Each intent runs a fixed, parameterised SQL query on semantic views. A sqlglot guard allows
   only `SELECT` on an allow-list of views. Row-level security is enforced in the database.
3. Results become a fact sheet. The model writes text with placeholders such as `{{f:db2_ist}}`;
   numbers are filled in by code, never typed by the model.
4. A verifier parses every number in the final text and rejects the answer unless each figure
   is written exactly as the fact sheet renders one of its facts. Any other notation
   ("6 Millionen Euro", "EUR 6 Mio.", figures in words) was typed by the model and is refused.
   After two failed rewrites the assistant falls back to a template answer.

The evaluation runs a second, deliberately hostile model that appends invented figures in eight
notations. It must not get a single one through. With the current verifier it does not; an earlier
version of the verifier let figures in non-standard notation pass
([details](docs/ergebnisse/README.md#q3-can-ai-write-the-month-end-commentary-with-correct-figures)).
What no number check can catch is a real figure under the wrong label; labels are fixed by the
templates.

## Not built yet (needs accounts or a real client)

- SAP HANA Cloud, Datasphere and a CAP service on BTP: need SAP trial accounts.
- SAC Planning: model design and import files are ready ([sac](sac)); building the story and data actions needs an SAC tenant.
- Snowflake: the run was done by hand on 2026-11-09 ([snowflake_run.json](docs/ergebnisse/snowflake_run.json)).
  A workflow that repeats it and compares 71 figures with DuckDB exists ([snowflake.yml](.github/workflows/snowflake.yml))
  but has not run yet; it needs the key in the GitHub environment `snowflake` ([runbook](docs/betrieb/runbook.md), section 6).
- Azure OpenAI evaluation: the first run is in `docs/ergebnisse/q3_eval_azure_first_run.json`; the routing
  change made after it has not been measured with a real model yet ([eval-azure.yml](.github/workflows/eval-azure.yml)).
  Support for reasoning models (gpt-5 family) is tested against a fake client only.
- Teams via Copilot Studio, Power Automate approval, RAG over Azure AI Search: planned, not built.
- Time-saving measurement (Q3): needs a practising controller.

## License

MIT. Data is simulated; any resemblance to real companies is coincidental.
