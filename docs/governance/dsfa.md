# Datenschutz-Folgenabschätzung (Art. 35 DSGVO): Schwellwertanalyse und Kurz-DSFA

Stand 2026-11-08. Gegenstand: Planwerk mit KI-Controlling-Assistent beim Einsatz mit Echtdaten eines Kunden.

## 1. Schwellwertanalyse

Geprüft gegen Art. 35 Abs. 3 DSGVO, die DSK-Liste der Verarbeitungen, für die eine DSFA durchzuführen ist
(Muss-Liste), und die neun Kriterien der Leitlinien WP 248 rev.01.

| Kriterium (WP 248) | Erfüllt? | Begründung |
|---|---|---|
| Bewertung/Scoring, Profiling | Nein | Kennzahlen je Gesellschaft, Produktgruppe, Kostenstelle; keine Bewertung von Personen |
| Automatisierte Entscheidung mit Rechtswirkung | Nein | Assistent erstellt Texte; Entscheidungen trifft der Mensch |
| Systematische Überwachung | Nein | Audit-Log dient Sicherheit/Nachvollziehbarkeit, keine Verhaltensauswertung (organisatorisch untersagt) |
| Sensible Daten (Art. 9/10) | Nein | Keine; Personalkosten nur aggregiert |
| Umfangreiche Verarbeitung | Nein | Ein Unternehmen, wenige Nutzer |
| Abgleich/Zusammenführung von Datensätzen | Teilweise | ERP-Daten werden integriert, aber zweckgleich (Controlling) |
| Schutzbedürftige Betroffene | Nein | – |
| Innovative Technologie | **Ja** | Einsatz eines großen Sprachmodells |
| Hinderung an Rechtsausübung | Nein | – |

**Ergebnis:** Ein Kriterium erfüllt; nach WP 248 ist eine DSFA in der Regel erst ab zwei Kriterien angezeigt.
Eine DSFA ist **nicht verpflichtend**. Wegen des Sprachmodells wird freiwillig die folgende Kurz-DSFA geführt.

## 2. Kurz-DSFA: Risiken und Maßnahmen

| Risiko | Eintritt / Schwere vor Maßnahmen | Maßnahmen | Restrisiko |
|---|---|---|---|
| Offenlegung von Kostenstellendaten an Unberechtigte über den Assistenten | mittel / mittel | Zeilenberechtigung in der Datenbank, Rollenprüfung je Intent, Identität aus Sitzung statt Prompt; 40 Angriffe getestet, 0 erfolgreich | gering |
| Prompt-Injection führt zu Datenabfluss oder Fehlaussagen | mittel / mittel | Geschlossene Intents, SQL-Guard (nur SELECT auf freigegebene Sichten), Eingabefilter, Verifier für jede Zahl, Test mit absichtlich feindlichem Modell | gering |
| Falsche Zahlen im Managementbericht | mittel / hoch (Vertrauensverlust, Fehlentscheidung) | Faktenblatt aus SQL, Platzhalter statt Zahlen im Modell, Verifier blockiert jede ungeprüfte Zahl, Rückfall auf geprüften Entwurf, Freigabe durch Controller | gering |
| Übermittlung von Fragen an den Modellanbieter | hoch / gering | EU Data Zone, AVV, keine Personen-Daten in Antworten, Fragen enthalten typischerweise keine personenbezogenen Daten; Hinweis in der Oberfläche | gering |
| Leistungskontrolle über Audit-Log | gering / mittel | Zweckbindung, Zugriff nur Plattform-Owner, Betriebsvereinbarung, Pseudonymisierungsoption `PLANWERK_AUDIT_REDACT` | gering |

**Gesamtergebnis:** Restrisiko gering; Verarbeitung kann aufgenommen werden. Überprüfung bei
wesentlichen Änderungen (anderes Modell, neue Datenquellen mit Personenbezug, Ausweitung des Nutzerkreises).
