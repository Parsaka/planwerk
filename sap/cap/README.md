# Planwerk on SAP BTP: CAP service and SAP HANA Cloud

Read-only OData V4 service on the controlling marts, built with the SAP Cloud Application
Programming Model (Node.js). All figures are **simulated** (fictional Nordwerk GmbH).

| Part | File |
|---|---|
| Data model (deployed to SAP HANA Cloud as HDI tables) | `db/schema.cds` |
| Initial data, exported from the dbt semantic views | `db/data/*.csv` (`npm run data`) |
| Service with role checks | `srv/controlling-service.cds`, `srv/controlling-service.js` |
| Roles and the `kostenstelle` attribute (XSUAA) | `xs-security.json` |
| Deployment to Cloud Foundry + HANA Cloud | `mta.yaml` |
| Tests (SQLite in memory, mocked users) | `test/controlling.test.js` |

**Authorisation** follows the same rule as the Snowflake row access policy and the AI assistant:
`Controller` sees everything; `CostCentreOwner` reads `Kostenstellen` and `Kostenarten` only for
the cost centres in the user attribute `kostenstelle` (instance-based `@restrict ... where`).

```bash
npm ci
npm test              # 8 tests: anonymous 401, wrong role 403, owner filter, bridge closes, ...
npx cds watch         # http://localhost:4004, users: controller, leitung_instandhaltung, gast (no password)
npx cds build --production   # HDI artefacts (.hdbtable/.hdbview) in gen/db
```

**Deploy (needs an SAP BTP trial with SAP HANA Cloud):**

```bash
cf login -a https://api.cf.<region>.hana.ondemand.com
mbt build && cf deploy mta_archives/planwerk-cap_0.1.0.mtar
```

Then assign the role collections `Planwerk_Controller` / `Planwerk_CostCentreOwner` in the BTP
cockpit (Security, Users) and set the `kostenstelle` attribute for owners.
