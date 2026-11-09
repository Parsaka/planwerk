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

1. Konto anlegen (Region AWS/Azure EU Frankfurt), Admin-User mit MFA.
2. Schlüsselpaare erzeugen und das Einrichtungsskript füllen: `python scripts/snowflake_keys.py`
   schreibt `keys/planwerk_ci.p8`, `keys/planwerk_assistant.p8` (privat, nie einchecken) und
   `keys/bootstrap.rendered.sql` (enthält nur öffentliche Schlüssel).
3. `keys/bootstrap.rendered.sql` in ein Snowsight-Worksheet kopieren, Rolle `ACCOUNTADMIN`, „Run all“.
   Die letzte Ergebniszeile zeigt den Konto-Bezeichner (`ORG-KONTO`). Alternative: Terraform,
   `cd infra/terraform/snowflake && terraform apply -var loader_rsa_public_key=... -var assistant_rsa_public_key=...`.
4. GitHub, Settings → Environments → `snowflake` anlegen:
   Secret `SNOWFLAKE_PRIVATE_KEY` = Inhalt von `keys/planwerk_ci.p8`, Variable `SNOWFLAKE_ACCOUNT` = Konto-Bezeichner
   (optional `SNOWFLAKE_USER`, Standard `PLANWERK_CI`). Der private Schlüssel gehört nur in dieses Secret,
   nicht in einen Chat, ein Ticket oder eine Datei im Repository.
5. Actions → „snowflake-run“ → Run workflow. Zuerst Profil `ci` (rund 2 Minuten), danach `dev`.
   Der Lauf erzeugt die Daten, lädt `S4_RAW`, baut und testet dbt auf Snowflake, baut dasselbe Projekt
   auf DuckDB und vergleicht 71 Kennzahlen aus 18 Tabellen beider Warehouses (`planwerk.load.snowflake_compare`).
   Ergebnis: `docs/ergebnisse/snowflake_run.json` und die Zusammenfassung des Laufs.

Lokal statt über GitHub: `SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=PLANWERK_CI SNOWFLAKE_PRIVATE_KEY_PATH=keys/planwerk_ci.p8`
setzen, dann `python -m planwerk.load.snowflake`, `PLANWERK_TARGET=snowflake make dbt`,
`python -m planwerk.load.snowflake_compare`.

Stand: Der Snowflake-Pfad ist ohne Konto so weit geprüft, wie es ohne Konto geht (dbt parst das Projekt für
das Ziel `snowflake`, Ladeanweisungen und Vergleichslogik sind getestet). Der erste echte Lauf kann trotzdem
an Snowflake-Eigenheiten scheitern; dann die Fehlermeldung des fehlgeschlagenen Schritts prüfen.

| Symptom im Lauf | Ursache | Maßnahme |
|---|---|---|
| `JWT token is invalid` | Öffentlicher Schlüssel am Benutzer passt nicht zum Secret, oder Konto-Bezeichner falsch | `desc user PLANWERK_CI` (Feld `RSA_PUBLIC_KEY_FP`) prüfen, Schritte 2 bis 4 wiederholen |
| `invalid identifier 'PERIOD'` in einem Staging-Modell | `S4_RAW` wurde mit einem Loader vor dem 09.11.2026 geladen (Spalten klein geschrieben) | Laden wiederholen; `create or replace` ersetzt die Tabellen |
| Vergleich meldet Abweichung | Unterschiedliches SQL-Verhalten der beiden Engines | Betroffenes Modell in `snowflake_run.json` ablesen, Ausdruck portabel formulieren, Test ergänzen |
| Marts leer für einen Fachbenutzer | Benutzername fehlt in `dbt/seeds/cost_centre_access.csv` | Zeile ergänzen, `dbt seed` und `dbt build`; die dbt-Rolle selbst ist von der Zeilenberechtigung ausgenommen |

### Azure OpenAI

1. Im Azure-Portal die Cloud Shell (Bash) öffnen und ausführen:
   `curl -fsSL https://raw.githubusercontent.com/Parsaka/planwerk/main/infra/azure/cloudshell_setup.sh | bash`.
   Das Skript legt ein Azure-OpenAI-Konto ohne API-Schlüssel (nur Entra ID) und ein Modell-Deployment
   `planwerk-chat` an und richtet die Anmeldung von GitHub Actions per OIDC ein. Es probiert der Reihe nach
   `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5-mini`, `gpt-5-nano`. Die beiden ersten führt Microsoft als abgekündigt
   (Abschaltung 14.04.2027) und kann sie neuen Abonnements verweigern; am 09.11.2026 ließ sich `gpt-4o-mini`
   in diesem Abonnement noch anlegen. Spätestens zur Abschaltung auf `gpt-5-mini` wechseln.
   Alternative: Terraform, `cd infra/terraform/azure && terraform apply -var subscription_id=...`.
2. Die sieben Zeilen der Ausgabe (keine Geheimnisse) als Datei `infra/azure/planwerk.env` einchecken oder als
   Repository-Variablen anlegen: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_MODEL`,
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (`AZURE_OPENAI_SKU` ist nur Information).
3. GitHub-Environment `eval` anlegen (Reviewer empfohlen).
4. Actions → „eval-azure-openai“ starten (startet auch von selbst, wenn `infra/azure/planwerk.env` sich ändert).
   Dauer rund 20 Minuten bei 30.000 Tokens pro Minute, Kosten deutlich unter 1 EUR. Ergebnis:
   `docs/ergebnisse/q3_eval_azure.json`.

Schlägt die Anmeldung im Workflow mit `AADSTS700213 No matching federated identity record` fehl, passt der
Betreff des GitHub-Tokens nicht zum hinterlegten Eintrag: Repositories, die nach dem 15.07.2026 angelegt
wurden, senden die unveränderliche Form mit numerischen Kennungen
(`repo:Parsaka@115464667/planwerk@1449783613:environment:eval`). Das Skript ab dem 09.11.2026 trägt beide
Formen ein; für eine ältere Einrichtung genügt es, das Skript erneut auszuführen (es ändert nichts
Bestehendes) oder den Eintrag einzeln anzulegen:

```bash
az ad app federated-credential create --id <AZURE_CLIENT_ID> --parameters '{"name":"github-planwerk-eval-immutable",
  "issuer":"https://token.actions.githubusercontent.com","audiences":["api://AzureADTokenExchange"],
  "subject":"repo:Parsaka@115464667/planwerk@1449783613:environment:eval"}'
```

Lesen des Ergebnisses: `usage.fallbacks` zählt Modellaufrufe, die nach sechs Wiederholungen (Drosselung,
Zeitüberschreitung, Störung) ohne Modell beantwortet wurden, also mit dem regelbasierten Router oder dem
Vorlagentext. Die Zahlen bleiben dann richtig, der Lauf sagt aber weniger über das Modell. Bei einem Wert
über null den Lauf wiederholen oder die Kapazität des Deployments erhöhen.

Das Modell muss weder Temperatur noch `max_tokens` unterstützen: Der Anbieter-Baustein erkennt
Reasoning-Modelle (`gpt-5*`, `o*`) am Modellnamen und sonst an der Fehlermeldung des Dienstes und sendet dann
`max_completion_tokens`. Einstellungen: `AZURE_OPENAI_API_VERSION` (Standard `2024-10-21`; `v1` für den versionslosen Endpunkt), `AZURE_OPENAI_MODEL_FAMILY`,
`AZURE_OPENAI_REASONING_EFFORT` (Standard `low`).

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
