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
| Q3 | Can AI write the German month-end commentary with 100 % correct figures and save half the controller's time? | 39/39 commentaries with every figure correct, also with a deliberately hostile model; 200/200 golden-set questions; 0 of 80 injection attempts succeeded. With Azure OpenAI gpt-4o-mini: 39/39 commentaries correct, 199/200 golden set, 36/40 on held-out paraphrases. Time saving needs a practising controller: **open.** |

Negative results are reported as negative; thresholds were not moved. Details, caveats and
the multi-seed robustness check are on the [results page](docs/ergebnisse/README.md).

## What is in the repository

```
SAP S/4HANA-shaped tables (ACDOCA, ACDOCP, BKPF/BSEG, VBAK/VBAP/VBRK/VBRP, EKKO/EKPO, AFKO, MARA/MARC/MBEW, KNA1, LFA1, CSKS ...)
        │  src/planwerk/generator   seeded simulation, real macro drivers, ground-truth manifest
        ▼
dbt (DuckDB locally, also run on Snowflake)
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
4. A verifier parses every number in the final text (German format, units, rounding) and
   rejects the answer if any number is not in the fact sheet. After two failed rewrites the
   assistant falls back to a template answer.

The evaluation runs a second, deliberately hostile model that invents numbers and swaps years.
It must not get a single wrong figure through. It did not.

## Running in the cloud

- **Snowflake** (trial, AWS eu-central-1): `make snowflake` loads 27 tables (6.27 million rows) with a
  key-pair service user, and the same dbt project builds 98/98 green. Every comparable relation
  matches DuckDB to the cent, and the row access policy shows each cost-centre owner only their own
  cost centres ([details](docs/ergebnisse/README.md#the-same-warehouse-on-snowflake)).
- **Azure OpenAI** (gpt-4o-mini, EU data zone, no API keys): the Q3 evaluation runs in GitHub Actions
  through OIDC ([eval-azure.yml](.github/workflows/eval-azure.yml)). The first run failed at
  91/200 because the model was routing alone. The final run has the rule parser first and scores
  199/200 ([details](docs/ergebnisse/README.md#with-the-real-model-azure-openai-gpt-4o-mini)).
  Method and governance questions are answered from the project documents through Azure AI Search
  (free tier, no keys), with the source section and no number that is not in the documents
  ([details](docs/ergebnisse/README.md#method-and-governance-questions-from-the-documents-rag)).
- **SAP BTP with HANA Cloud** (trial, US East): the CAP service ([sap/cap](sap/cap)) runs on Cloud
  Foundry with an HDI container and XSUAA. A live smoke test reads the same figures as the warehouse
  to the cent, refuses requests without a token and refuses writes
  ([details](docs/ergebnisse/README.md#the-cap-service-on-sap-btp-with-hana-cloud)).
- **SAP Analytics Cloud and SAP Datasphere** (trials): the SAC planning model holds 21,000 rows that
  match the warehouse to the cent on shared dimensions with an account hierarchy (DB I > DB II >
  DB III > BE). Data actions build the 6+6 forecast and the driver-based budget 2026 (units × price),
  and a story shows the hierarchy against Budget. Datasphere computes the same DB I in a view and an
  analytic model, and a data access control shows each cost-centre owner only their cost centres
  ([details](docs/ergebnisse/README.md#sap-analytics-cloud-and-sap-datasphere)).

## Not built yet (needs accounts or a real client)

- SAC data access per cost-centre owner: needs real SAC user IDs (the trial has one user); built in Datasphere instead.
- Teams via Copilot Studio and Power Automate approval: need a Microsoft 365 business tenant.
- Time-saving measurement (Q3): needs a practising controller.

## License

MIT. Data is simulated; any resemblance to real companies is coincidental.
