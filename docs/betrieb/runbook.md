# Runbook Planwerk

Zielgruppe: Plattform-Owner und Vertretung. Alle Befehle aus dem Repository-Wurzelverzeichnis.

## 1. Lokaler Gesamtlauf (ohne Cloud)

```bash
make install                       # Python-Pakete inkl. dbt-duckdb, LangGraph, MCP
make all PROFILE=dev               # Generator -> dbt build -> Forecast -> Backtest -> Liquidität -> Eval -> Berichte
make assistant Q="Warum liegt der DB II in Österreich unter Plan?"
```

| Schritt | Dauer (dev) | Ergebnis | Erfolgskriterium |
|---|---|---|---|
| `make generate` | ≈ 1 min | `data/raw/*.parquet`, `manifest.json`, `ground_truth.json` | 27 Tabellen, ≈ 2,4 Mio. ACDOCA-Zeilen |
| `make dbt` | ≈ 2 min | `data/warehouse/planwerk.duckdb` | `PASS=98 ERROR=0` |
| `make forecast liquidity` | < 1 min | `forecast.*`, `semantic.sem_prognose`, CSV | 9 Forecast-Zeilen je Bereich, 13 Wochen je Gesellschaft |
| `make backtest` | ≈ 25 min | `docs/ergebnisse/q2_backtest_*` | 200 Szenarien |
| `make eval` | < 1 min | `docs/ergebnisse/q3_eval.json` | Exit-Code 0 |
| `make test` | ≈ 3 min | pytest | alle grün |

## 2. Monatsabschluss-Routine (Zielbetrieb)

1. **WT+2:** Extrakt aus S/4HANA (CDS-Views bzw. Tabellen laut Datenvertrag) nach `S4_RAW` laden:
   `python -m planwerk.load.snowflake`. Der Loader bricht ab, wenn Zeilenzahlen nicht zum Manifest passen.
2. **WT+2:** `PLANWERK_TARGET=snowflake make dbt`. Bei Testfehlern **keine** Berichte erzeugen; Fehlerbild
   prüfen (Kap. 3).
3. **WT+3:** Datenqualitätsbericht `controlling.mart_data_quality_findings` sichten; harte Regeln müssen leer sein.
4. **WT+3:** `make forecast liquidity reports`; Monatskommentar-Entwürfe je Gesellschaft über den Assistenten.
5. **WT+4:** Controller prüft und gibt Kommentare frei (Power-Automate-Freigabe); Versand Monatsbericht.

## 3. Fehlerbilder

| Symptom | Ursache (typisch) | Maßnahme |
|---|---|---|
| `assert_documents_balance` rot | Unvollständiger Extrakt (Beleg ohne Gegenzeile) | Extrakt wiederholen; Belegnummern aus Testausgabe mit Quellsystem abgleichen |
| `assert_sales_items_match_gl` rot | Faktura ohne FI-Beleg oder umgekehrt | Abgrenzung des Extraktzeitraums prüfen |
| `assert_bab_fully_allocated` rot | Neue Kostenstelle ohne Umlageschlüssel | Schlüssel in `ALLOC_KEYS` bzw. Seed `bab_cycle` ergänzen |
| `dbt_expression_cost_centre_resolved` rot | Buchung auf Kostenstelle außerhalb Gültigkeit | Stammdatenpflege (CSKS) bzw. SCD2-Zeitraum prüfen |
| Assistent antwortet „konnte nicht mit geprüften Zahlen erstellt werden“ | Modell lieferte Zahl außerhalb des Faktenblatts, Rückfall versagte | Audit-Log (`status = error`) prüfen, Frage im Golden Set ergänzen |
| Snowflake-Warehouse suspendiert | Resource Monitor hat Monatskontingent erreicht | Ursache in `QUERY_HISTORY` prüfen; Quote nur per Pull Request auf `monthly_credit_quota` erhöhen |
| Azure-Budgetalarm | Token-Verbrauch | `cost_eur` im Audit-Log je Nutzer prüfen; Kapazität `openai_capacity_k_tpm` begrenzt Durchsatz hart |

## 4. Überwachung (wöchentlich)

* Audit-Log: `status in (blocked, denied, error)` je Nutzer; Häufungen an Datenschutz/Controlling melden.
* Kosten: Snowflake `METERING_HISTORY`, Azure Cost Management (Budget `budget-planwerk`).
* CI: Eval-Ergebnis des letzten Laufs (Artefakt `q3-eval-ci`).

## 5. Wiederanlauf und Datensicherung

* Simulierte Daten sind vollständig reproduzierbar: `make generate SEED=42` erzeugt bitgleiche Daten
  (Test `test_generator_is_deterministic`).
* Snowflake: Time Travel 7 Tage (`data_retention_time_in_days`); versehentlich gelöschte Tabelle mit
  `undrop table` wiederherstellen. Marts sind jederzeit per `make dbt` neu aufbaubar.
* Infrastruktur: `terraform apply` aus `infra/terraform/*` stellt Konfiguration wieder her (State im
  Azure-Storage-Backend, Versionierung aktiv).
* Wiederherstellungstest jährlich: frische Umgebung, Gesamtlauf, Abgleich `docs/ergebnisse` mit Vorjahr.

## 6. Ersteinrichtung Cloud

### Snowflake (Trial, 30 Tage)
1. Konto anlegen (Region AWS/Azure EU Frankfurt), Admin-User mit MFA.
2. Schlüsselpaare erzeugen: `openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out ci_key.p8`,
   `openssl rsa -in ci_key.p8 -pubout -out ci_key.pub` (dasselbe für den Assistenten).
3. `cd infra/terraform/snowflake && terraform init && terraform apply -var loader_rsa_public_key=... -var assistant_rsa_public_key=...`
4. GitHub: Secret `SNOWFLAKE_PRIVATE_KEY` (Inhalt `ci_key.p8`) in Environment `snowflake`, Variablen
   `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER=PLANWERK_CI`.
5. `python -m planwerk.load.snowflake` und `PLANWERK_TARGET=snowflake make dbt`.

### Azure OpenAI
1. Subscription mit Zugriff auf Azure OpenAI; `cd infra/terraform/azure && terraform apply -var subscription_id=...`.
2. GitHub-Environment `eval` anlegen (Reviewer erforderlich), Variablen aus den Terraform-Outputs:
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`.
3. Workflow „eval-azure-openai“ manuell starten.

### Schlüsselrotation
Halbjährlich: neues Schlüsselpaar, `rsa_public_key_2` setzen, Secret tauschen, alten Schlüssel entfernen.

### Rückbau
`terraform destroy` in beiden Stacks; Snowflake-Trial endet automatisch.

## 7. Kontakte und Eskalation

| Thema | Erste Stelle | Eskalation |
|---|---|---|
| Fachliche Zahlenfragen | Controlling | Leitung Controlling |
| Plattform, Ladefehler | Plattform-Owner | Implementierungspartner |
| Datenschutz, Berechtigungen | Datenschutz | Geschäftsführung |
