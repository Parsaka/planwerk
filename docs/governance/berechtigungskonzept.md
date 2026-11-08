# Berechtigungskonzept Planwerk

| | |
|---|---|
| Version | 1.0 (2026-11-08) |
| Geltungsbereich | Planwerk-Plattform: Warehouse (DuckDB lokal / Snowflake), SAC-Planung, KI-Controlling-Assistent, CI/CD |
| Datenbasis | Simulierte Daten der fiktiven Nordwerk GmbH (keine personenbezogenen Echtdaten) |
| Verantwortlich | Leitung Controlling (fachlich), Plattform-Owner (technisch) |

## 1. Grundsätze

1. **Need-to-know und Least Privilege:** Jede Rolle erhält nur die Daten, die sie für ihre Aufgabe braucht.
2. **Funktionstrennung (SoD):** Wer Daten lädt, transformiert oder Infrastruktur ändert, genehmigt keine
   Plan- oder Ist-Werte; Planfreigaben erfolgen in SAC durch die Geschäftsführung.
3. **Technische Durchsetzung statt Vertrauen:** Zeilenberechtigungen sitzen in der Datenbank (Row Access
   Policy bzw. gefilterte semantische Sichten), nicht in der Oberfläche. Der KI-Assistent fragt mit der
   Identität des anfragenden Nutzers ab und kann Berechtigungen weder erweitern noch umgehen.
4. **Keine geteilten oder persönlichen Passwörter für Maschinen:** Service-User nur mit Schlüsselpaar
   (Snowflake) bzw. Workload-Identität (Azure, GitHub OIDC).

## 2. Rollen

| Rolle | Wer | Daten | Technische Rolle |
|---|---|---|---|
| Controller (`CONTROLLER`) | Controlling-Team | Alle Gesellschaften, alle Kostenstellen, alle Auswertungen, Monatskommentar | Snowflake `PLANWERK_REPORTER`; Zugriffsliste `cost_centre = *` |
| Geschäftsführung (`MANAGEMENT`) | GF Gruppe | Wie Controller, lesend; Planfreigabe in SAC | `PLANWERK_REPORTER` |
| Kostenstellenverantwortliche (`CC_OWNER`) | z. B. Leitung Instandhaltung | Nur eigene Kostenstellen (Kostenarten-Detail, Abweichungen); keine Ergebnis- oder Gesellschafts-KPIs | `PLANWERK_REPORTER` + Row Access Policy |
| KI-Assistent (technisch) | Service-User `PLANWERK_ASSISTANT` | Nur Schema `SEMANTIC`, nur lesend; zusätzlich Zeilenfilter des anfragenden Nutzers | `PLANWERK_ASSISTANT` |
| Datenbeladung | Service-User `PLANWERK_CI` | Schreibt nur `RAW` | `PLANWERK_LOADER` |
| Transformation | Service-User `PLANWERK_CI` (dbt) | Liest `RAW`, besitzt `STAGING` bis `SEMANTIC` | `PLANWERK_TRANSFORMER` |
| Plattform-Admin | 1 benannte Person + Vertretung | Infrastruktur (Terraform), keine fachlichen Freigaben | `ACCOUNTADMIN` nur per Break-Glass |

Die Zuordnung Nutzer → Kostenstelle ist versioniert in
[`dbt/seeds/cost_centre_access.csv`](../../dbt/seeds/cost_centre_access.csv) (Tabelle
`reference.cost_centre_access`). Änderungen nur per Pull Request mit Review durch die Leitung Controlling.

## 3. Technische Umsetzung

| Ebene | Mechanismus | Nachweis |
|---|---|---|
| Snowflake | Rollenhierarchie, Grants je Schema, Future Grants, Resource Monitor | [`infra/terraform/snowflake/main.tf`](../../infra/terraform/snowflake/main.tf) |
| Zeilen (Snowflake) | Row Access Policy `rap_cost_centre` auf Kostenstellen-Marts, `CURRENT_USER()` gegen Zugriffsliste | Makro `apply_cost_centre_policy` in [`dbt/macros/row_access.sql`](../../dbt/macros/row_access.sql) |
| Zeilen (lokal) | Semantische Sichten filtern auf Sitzungsvariable `planwerk_user` | `sem_kostenstellen`, `sem_kostenarten`; Test `test_row_level_security_restricts_cost_centre_owner` |
| KI-Assistent: Auswertung | Rollenprüfung je Intent (`CC_OWNER` nur Kostenstellen-Intents) | `tools.authorise`, Golden-Set-Kategorie `row_level_security` |
| KI-Assistent: SQL | Nur `SELECT` auf freigegebene Sichten, Zeilenlimit, verbotene Funktionen | [`sql_guard.py`](../../src/planwerk/assistant/sql_guard.py), Injection-Suite |
| KI-Assistent: Identität | Nutzer kommt aus der Sitzung bzw. vom Gateway, nie aus dem Prompt | `mcp_server._user`, Angriffe i13–i15, i22 |
| Azure OpenAI | Nur Entra-ID-Token, keine API-Schlüssel (`local_auth_enabled = false`); CI nur Rolle „OpenAI User“ | [`infra/terraform/azure/main.tf`](../../infra/terraform/azure/main.tf) |
| CI/CD | GitHub OIDC, geschützte Umgebung `eval`, Branch-Schutz auf `main` | [`.github/workflows`](../../.github/workflows) |

Antworten für fremde Kostenstellen unterscheiden nicht zwischen „keine Daten“ und „keine Berechtigung“,
damit die Existenz fremder Kostenstellen nicht offengelegt wird.

## 4. Prozesse

* **Beantragung:** Ticket mit Rolle und Kostenstellen; Genehmigung durch Leitung Controlling; Umsetzung
  per Pull Request auf die Zugriffsliste; dbt-Lauf aktiviert die Änderung.
* **Entzug:** Austritt oder Wechsel → Entfernen am selben Tag (HR-Meldung als Auslöser).
* **Rezertifizierung:** quartalsweise. Die Leitung Controlling prüft die Zugriffsliste; das Protokoll
  wird im Repository abgelegt (`docs/governance/rezertifizierung/JJJJ-Qn.md`).
* **Break-Glass:** `ACCOUNTADMIN` nur mit Vier-Augen-Freigabe, zeitlich begrenzt, protokolliert;
  Nachbericht innerhalb von zwei Arbeitstagen.

## 5. Protokollierung

Alle Anfragen an den KI-Assistenten werden im Audit-Log protokolliert (siehe [audit-log.md](audit-log.md)).
Snowflake-Zugriffe sind über `ACCOUNT_USAGE.ACCESS_HISTORY` und `LOGIN_HISTORY` nachvollziehbar.
