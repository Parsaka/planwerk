# ADR-0003: Local-first warehouse (DuckDB) with a Snowflake-portable dbt project

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

Snowflake, SAP BTP (HANA Cloud, Datasphere, SAC) and Azure trials are time-limited (typically
30 days). Booking them in week 1 wastes most of the trial before the layer that needs it exists.
Reviewers of a portfolio project also need to run it without any account.

## Decision

- The dbt project runs on **DuckDB** by default (`make dbt`) and on **Snowflake** with
  `PLANWERK_TARGET=snowflake`. SQL stays portable: cross-database macros (`dbt.datediff`,
  `dbt.concat`, own `period_of`), no DuckDB-only functions in models.
- Snowflake-specific features (row access policies, masking, warehouses, resource monitors)
  are in Terraform and in macros that only run on the Snowflake target.
- Trials are booked in the sprint in which the layer is built, not earlier.

## Consequences

- Every pull request runs the full pipeline in CI on DuckDB in a few minutes.
- A one-off Snowflake run proves portability; it is documented with screenshots and query
  history, not kept running (cost cap).
