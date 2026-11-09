# Infrastructure (Terraform)

Two independent stacks, both optional: the whole platform runs locally on DuckDB without them.

| Stack | What it creates | Cost cap |
|---|---|---|
| `snowflake/` | Database `PLANWERK` with 7 schemas, XS warehouse (auto-suspend 60 s), 4 least-privilege roles, 2 key-pair service users | Resource monitor: suspend at 100 % of `monthly_credit_quota` (default 10 credits), hard stop at 110 % |
| `azure/` | Azure OpenAI (EU data zone, keyless), Key Vault (RBAC), Log Analytics, optional AI Search (free), GitHub OIDC identity | Deployment capped at `openai_capacity_k_tpm` (default 30k tokens/min); budget alerts at 50/80/100 % of `monthly_budget_eur` (default 20 EUR) |

No credential is stored in code or state variables: Snowflake uses key-pair auth via
environment variables, Azure uses OIDC federation from GitHub Actions (`use_oidc = true`).
`terraform fmt -check` and `terraform validate` run in CI (`.github/workflows/ci.yml`).

```bash
cd infra/terraform/snowflake && terraform init && terraform plan -var-file=planwerk.tfvars
cd infra/terraform/azure     && terraform init && terraform plan -var subscription_id=<id>
```
Step-by-step setup, rotation and teardown: [docs/betrieb/runbook.md](../../docs/betrieb/runbook.md).
