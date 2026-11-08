# Kontrollmatrix (angelehnt an ISO/IEC 27001:2022, Anhang A)

Keine Zertifizierung; die Matrix zeigt, welche Kontrollen Planwerk umsetzt, wo sie implementiert sind
und wie sie geprüft werden. „Automatisch“ heißt: bei jedem CI-Lauf.

| Control (Anhang A) | Ziel | Umsetzung in Planwerk | Nachweis / Test | Prüfung |
|---|---|---|---|---|
| 5.15 Zugangssteuerung | Zugriff nur nach Bedarf | Rollenmodell, Zugriffsliste je Kostenstelle | [berechtigungskonzept.md](berechtigungskonzept.md), `cost_centre_access.csv` | quartalsweise Rezertifizierung |
| 5.18 Zugangsrechte | Vergabe, Änderung, Entzug geregelt | Änderung nur per Pull Request mit Review | Git-Historie der Zugriffsliste | quartalsweise |
| 8.3 Einschränkung des Informationszugriffs | Zeilenberechtigung | Row Access Policy (Snowflake), gefilterte Sichten (DuckDB) | `test_row_level_security_restricts_cost_centre_owner`, Golden Set `row_level_security` | automatisch |
| 8.2 Privilegierte Zugriffsrechte | Admin-Rechte minimal | `ACCOUNTADMIN` nur Break-Glass; CI ohne Admin-Rolle | Terraform-Rollen, Runbook Kap. 6 | halbjährlich |
| 8.5 Sichere Authentisierung | Keine Passwörter für Maschinen | Snowflake-Schlüsselpaar, Azure Entra ID, GitHub OIDC; Azure OpenAI ohne API-Schlüssel | `local_auth_enabled = false`, `use_oidc = true` | bei jeder Terraform-Änderung |
| 5.17 Authentisierungsinformationen | Geheimnisse geschützt | Key Vault (RBAC), GitHub Environments; nichts im Repository | `.gitignore` (`.env`, `*.tfstate`), Secret Scanning | automatisch (GitHub) |
| 8.9 Konfigurationsmanagement | Reproduzierbare Infrastruktur | Terraform für Snowflake und Azure | `terraform fmt -check`, `terraform validate` | automatisch |
| 8.25 Sicherer Entwicklungszyklus | Qualität vor Merge | Branch-Schutz, CI (Lint, Tests, dbt build, Eval), Definition of Done | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [DoD](../projekt/definition-of-done.md) | automatisch |
| 8.28 Sichere Programmierung | Injection verhindern | SQL nur aus geschlossenen Intents, `sqlglot`-Guard, Literale nur aus validierten Werten | `test_sql_guard_rejects`, Injection-Suite (40 Angriffe, normal und feindliches Modell) | automatisch |
| 8.29 Sicherheitstests | Angriffe testen | Prompt-Injection-, Rechteausweitungs-, Exfiltrations- und Fälschungsversuche | `eval/injection_suite.yaml`, Ergebnis in `docs/ergebnisse/q3_eval.json` | automatisch |
| 8.11 Datenmaskierung | Keine Echtdaten in Test | Ausschließlich simulierte Daten in Entwicklung und CI | Generator, ADR-0002 | bei jedem Lauf |
| 8.12 Verhinderung von Datenabfluss | KI gibt nur Freigegebenes aus | Nur semantische Sichten, Zeilenlimit 500, Ausgabefilter (Prompt-Leak), keine Rohdaten im Prompt | `guardrails.check_output`, Verifier | automatisch |
| 8.15 Protokollierung | Nachvollziehbarkeit | Audit-Log je Anfrage; Snowflake Access History; Azure Diagnostic Settings | [audit-log.md](audit-log.md), `test_audit_log_written` | automatisch + wöchentliche Sichtung |
| 8.16 Überwachung | Auffälligkeiten erkennen | Auswertung `status in (blocked, denied, error)`; Budget- und Credit-Alarme | Runbook Kap. 4 | wöchentlich |
| 8.24 Kryptografie | Verschlüsselung | TLS für alle Verbindungen; Snowflake und Azure verschlüsseln at rest (Anbieter-Standard) | Anbieter-Dokumentation | jährlich |
| 8.13 Datensicherung | Wiederherstellbarkeit | Quelldaten reproduzierbar (Generator + Seed); Snowflake Time Travel 7 Tage; Repository auf GitHub | Runbook Kap. 5 | jährlicher Wiederherstellungstest |
| 8.32 Änderungsmanagement | Kontrollierte Änderungen | Pull Requests, Reviews, Data Contracts auf Marts | `contract: enforced` in dbt | automatisch |
| 5.23 Cloud-Dienste | Anbieter gesteuert | EU-Regionen, Kostenobergrenzen, AVV | Terraform-Variablen `location`, Resource Monitor, Budget | jährlich |
| 5.34 Datenschutz / PII | DSGVO-Konformität | VVT, DSFA-Schwellwertanalyse, Aggregation von Personalkosten | [vvt.md](vvt.md), [dsfa.md](dsfa.md) | jährlich und bei Änderungen |
| 5.37 Dokumentierte Betriebsabläufe | Betrieb ohne Wissensinseln | Runbook mit Lade-, Prüf-, Wiederanlauf- und Notfallschritten | [runbook.md](../betrieb/runbook.md) | halbjährlich |
