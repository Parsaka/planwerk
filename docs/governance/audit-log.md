# Audit-Log des KI-Controlling-Assistenten

Jede Anfrage (Frage oder Monatskommentar) erzeugt genau einen Eintrag im Append-only-Log
(JSON Lines, Standard `data/audit/assistant_audit.jsonl`, konfigurierbar über `PLANWERK_AUDIT_LOG`).
Implementierung: [`src/planwerk/assistant/audit.py`](../../src/planwerk/assistant/audit.py).

## Felder

| Feld | Inhalt | Zweck |
|---|---|---|
| `request_id`, `ts` | UUID, Zeitstempel UTC | Eindeutigkeit, Reihenfolge |
| `user`, `role` | Benutzerkennung und Rolle aus der Zugriffsliste | Wer hat gefragt |
| `question` | Fragetext (bei `PLANWERK_AUDIT_REDACT=1` leer) | Nachvollziehbarkeit |
| `question_sha256`, `answer_sha256` | Hashes von Frage und Antwort | Integritätsnachweis ohne Volltext der Antwort |
| `status`, `block_category` | answered / fallback / blocked / denied / no_data / out_of_scope / error | Sicherheitsereignisse erkennen |
| `intent` | Erkannte Auswertung mit Parametern | Was wurde ausgewertet |
| `sql` | Alle tatsächlich ausgeführten, validierten SQL-Statements | Prüfbarkeit der Zahlenherkunft |
| `fact_ids`, `verified`, `unverified` | Verwendete Fakten, Verifier-Ergebnis | Nachweis „jede Zahl geprüft“ |
| `provider`, `prompt_tokens`, `completion_tokens`, `cost_eur` | Modell und Verbrauch | Kostenkontrolle je Antwort |
| `latency_ms`, `attempts` | Laufzeit, Anzahl Formulierungsversuche | Betrieb |

Abfrageergebnisse werden nicht protokolliert (das Warehouse bleibt das führende System); die Werte
lassen sich über `sql` jederzeit reproduzieren.

## Aufbewahrung und Zugriff

* Aufbewahrung 12 Monate, danach Löschung (Löschkonzept im VVT, Nr. 2).
* Lesezugriff: Plattform-Owner und Datenschutz auf Anfrage; kein Zugriff für Fachanwender.
* Integrität: Datei nur anhängend; in Azure-Betrieb Export nach Log Analytics (unveränderlich für 30 Tage),
  Hashes erlauben den Nachweis, dass eine gezeigte Antwort unverändert ist.
* Auswertung: wöchentlich `status in (blocked, denied, error)` sichten; Häufungen je Nutzer melden.
