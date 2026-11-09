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

Beide Cloud-Läufe sind optional und einmalig. Es gibt je zwei Wege: ein Skript für den Browser
(ohne lokale Werkzeuge) oder Terraform. Nur einen der beiden Wege verwenden.

### Snowflake (Trial, 30 Tage)

Der erste Lauf ist am 09.11.2026 von Hand erfolgt: 27 Tabellen geladen, dbt 98 von 98, Zahlen gleich wie auf
DuckDB ([snowflake_run.json](../ergebnisse/snowflake_run.json)). Für eine neue Umgebung:

1. Konto anlegen (Region AWS/Azure EU Frankfurt), Admin-User mit MFA.
2. Schlüsselpaare erzeugen und das Einrichtungsskript füllen: `python scripts/snowflake_keys.py`
   schreibt `keys/planwerk_ci.p8`, `keys/planwerk_assistant.p8` (privat, nie einchecken) und
   `keys/bootstrap.rendered.sql` (enthält nur öffentliche Schlüssel).
3. Das gefüllte Skript in ein Snowsight-Worksheet kopieren, Rolle `ACCOUNTADMIN`, „Run all“.
   Die letzte Ergebniszeile zeigt den Konto-Bezeichner (`ORG-KONTO`). Alternative: Terraform,
   `cd infra/terraform/snowflake && terraform apply -var loader_rsa_public_key=... -var assistant_rsa_public_key=...`.
4. Lauf vom Arbeitsplatz: `SNOWFLAKE_ACCOUNT=... SNOWFLAKE_PRIVATE_KEY_PATH=keys/planwerk_ci.p8 make snowflake`
   (laden, dann dbt mit allen Tests), danach `python -m planwerk.load.snowflake_compare`.
5. Wiederholbar ohne Arbeitsplatz: GitHub, Settings → Environments → `snowflake` anlegen mit Secret
   `SNOWFLAKE_PRIVATE_KEY` (Inhalt von `keys/planwerk_ci.p8`) und Variable `SNOWFLAKE_ACCOUNT`; dann
   Actions → „snowflake-run“. Der Lauf erzeugt die Daten, lädt `S4_RAW`, baut dbt auf Snowflake und auf
   DuckDB und vergleicht 71 Kennzahlen aus 18 Tabellen; Ergebnis in
   `docs/ergebnisse/snowflake_workflow_run.json`. Dieser Workflow ist noch nicht gelaufen. Der private
   Schlüssel gehört nur in das Secret, nicht in einen Chat, ein Ticket oder eine Datei im Repository.

Zeilenberechtigung beim Prüfen beachten: Der Dienstbenutzer `PLANWERK_CI` ist kein Kostenstellenverantwortlicher
und liest aus `controlling.mart_cost_variance` null Zeilen. Der Vergleich liest diese Tabelle deshalb als
Benutzer `CONTROLLER` (`EXECUTE USING POLICY_CONTEXT`). Folge für dbt auf Snowflake: der Test
`assert_cost_deviation_assigned` (Q1, Kriterium 3) sieht dort keine Zeilen und besteht ohne Aussage; maßgeblich
ist sein Ergebnis auf DuckDB.

| Symptom im Lauf | Ursache | Maßnahme |
|---|---|---|
| `JWT token is invalid` | Öffentlicher Schlüssel am Benutzer passt nicht zum Secret, oder Konto-Bezeichner falsch | `desc user PLANWERK_CI` (Feld `RSA_PUBLIC_KEY_FP`) prüfen, Schritte 2 bis 4 wiederholen |
| `invalid identifier 'PERIOD'` in einem Staging-Modell | `S4_RAW` mit einem Loader vor dem 09.11.2026 geladen (Spalten klein geschrieben) | Laden wiederholen; `create or replace` ersetzt die Tabellen |
| Vergleich meldet Abweichung | Unterschiedliches SQL-Verhalten der beiden Engines | Betroffene Tabelle im Ergebnis ablesen, Ausdruck portabel formulieren, Test ergänzen |
| Marts leer für einen Fachbenutzer | Benutzername fehlt in `dbt/seeds/cost_centre_access.csv` | Zeile ergänzen, dann `make snowflake-dbt` |

### Azure OpenAI

1. Im Azure-Portal die Cloud Shell (Bash) öffnen und ausführen:
   `curl -fsSL https://raw.githubusercontent.com/Parsaka/planwerk/main/infra/azure/cloudshell_setup.sh | bash`.
   Das Skript legt ein Azure-OpenAI-Konto ohne API-Schlüssel (nur Entra ID) und ein Deployment `gpt-4o-mini`
   an und richtet die Anmeldung von GitHub Actions per OIDC ein. Alternative: Terraform,
   `cd infra/terraform/azure && terraform apply -var subscription_id=...`.
2. Die Zeilen der Ausgabe (keine Geheimnisse) stehen in `infra/azure/planwerk.env`; alternativ als
   Repository-Variablen: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_CLIENT_ID`,
   `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, optional `AZURE_OPENAI_MODEL`.
3. GitHub-Environment `eval` anlegen (Reviewer empfohlen).
4. Actions → „eval-azure-openai“ starten (startet auch von selbst, wenn `infra/azure/planwerk.env` sich ändert).
   Ergebnis: `docs/ergebnisse/q3_eval_azure.json`. Der erste Lauf am 09.11.2026
   (`q3_eval_azure_first_run.json`) dauerte 27 Minuten bei 10.000 Tokens pro Minute (387 Modellaufrufe,
   283.000 + 46.000 Tokens); damals ordnete das Modell jede Frage selbst zu. Seit die Regeln zuerst zuordnen,
   fallen die meisten Zuordnungsaufrufe weg.

Schlägt die Anmeldung mit `AADSTS700213 No matching federated identity record` fehl, passt der Betreff des
GitHub-Tokens nicht zum hinterlegten Eintrag: Repositories, die nach dem 15.07.2026 angelegt wurden, senden
die Form mit numerischen Kennungen (`repo:Parsaka@115464667/planwerk@1449783613:environment:eval`). Das
Skript trägt seit dem 09.11.2026 beide Formen ein; erneut ausführen genügt.

Lesen des Ergebnisses: `usage.rule_routed` und `usage.model_routed` zeigen, wer wie viele Fragen zugeordnet hat.
`usage.fallbacks` zählt Modellaufrufe, die nach sechs Wiederholungen (Drosselung, Zeitüberschreitung, Störung)
ohne Modell beantwortet wurden: die Frage bleibt dann „außerhalb des Auftrags“ oder die Antwort ist der
Vorlagentext. Die Zahlen bleiben dann richtig, der Lauf sagt aber weniger über das Modell. Bei einem Wert
über null den Lauf wiederholen oder die Kapazität des Deployments erhöhen.

Modellwechsel: `gpt-4o-mini` schaltet Microsoft am 14.04.2027 ab. Der Anbieter-Baustein unterstützt auch
Reasoning-Modelle (`gpt-5-mini` und andere), die weder Temperatur noch `max_tokens` annehmen: Er erkennt sie am
Modellnamen (`AZURE_OPENAI_MODEL` oder Name des Deployments), sonst an der Fehlermeldung des Dienstes, und
sendet dann `max_completion_tokens`. Einstellungen: `AZURE_OPENAI_API_VERSION` (Standard `2024-10-21`; `v1` für
den versionslosen Endpunkt), `AZURE_OPENAI_MODEL_FAMILY`, `AZURE_OPENAI_REASONING_EFFORT` (Standard `low`).
Dieser Pfad ist mit einem nachgebildeten Client getestet, nicht gegen ein echtes Reasoning-Deployment.

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
