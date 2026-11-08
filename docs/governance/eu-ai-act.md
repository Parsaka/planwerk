# Einordnung nach EU AI Act (Verordnung (EU) 2024/1689)

Stand 2026-11-08. Gegenstand: KI-Controlling-Assistent von Planwerk.

## 1. Rollen

* **Betreiber (Deployer, Art. 3 Nr. 4):** das Unternehmen, das den Assistenten intern nutzt.
* **Anbieter des KI-Systems (Art. 3 Nr. 3):** wer den Assistenten unter eigenem Namen bereitstellt
  (hier: das Projekt bzw. der Implementierungspartner).
* **Anbieter des KI-Modells mit allgemeinem Verwendungszweck (GPAI):** der Modellanbieter (OpenAI über
  Microsoft Azure). Dessen Pflichten nach Art. 53 ff. liegen beim Modellanbieter.

## 2. Risikoklasse

| Prüfung | Ergebnis |
|---|---|
| Verbotene Praktiken (Art. 5) | Nein. Keine Manipulation, kein Social Scoring, keine Emotionserkennung am Arbeitsplatz |
| Hochrisiko nach Anhang I (Produktsicherheit) | Nein. Kein Sicherheitsbauteil eines regulierten Produkts |
| Hochrisiko nach Anhang III | Nein. Nicht Nr. 4 (Beschäftigung: keine Entscheidungen über Einstellung, Beförderung, Aufgabenzuweisung oder Leistungsbewertung von Personen), nicht Nr. 5 (keine Kreditwürdigkeitsprüfung natürlicher Personen). Unternehmensinterne Finanzberichterstattung ist kein Anhang-III-Bereich |
| Transparenzpflichten (Art. 50) | Ja, sinngemäß: Nutzer werden informiert, dass sie mit einem KI-System interagieren; erzeugte Texte sind als KI-Entwurf gekennzeichnet |

**Ergebnis:** KI-System mit **geringem Risiko** mit Transparenzpflichten. Keine Konformitätsbewertung, keine
Registrierung in der EU-Datenbank erforderlich.

Ausschlusskriterium für die Zukunft: Würde der Assistent genutzt, um Kostenstellenverantwortliche oder
andere Beschäftigte zu bewerten (z. B. Ranking als Grundlage für Zielvereinbarungen oder Boni), fiele er
unter Anhang III Nr. 4 b). Diese Nutzung ist im Lastenheft ausgeschlossen.

## 3. Umgesetzte Pflichten und freiwillige Maßnahmen

| Pflicht / Maßnahme | Umsetzung |
|---|---|
| KI-Kompetenz (Art. 4, gilt seit 02.02.2025) | Key-User-Schulung mit Modul „Grenzen des Assistenten, Prüfpflicht, Verifier“ (Schulungsunterlage W12) |
| Transparenz (Art. 50) | Hinweis in Oberfläche und Antwort („Simulierte Daten“, „KI-Entwurf, von Controlling freizugeben“) |
| Menschliche Aufsicht (freiwillig, analog Art. 14) | Monatskommentar ist Entwurf; Freigabe durch Controller (Power-Automate-Freigabe vorgesehen) |
| Genauigkeit und Robustheit (freiwillig, analog Art. 15) | Fact-first-Architektur, Verifier, Golden Set (200 Fragen), Kommentar-Testset (39), Injection-Suite (40), Evaluation in CI |
| Protokollierung (freiwillig, analog Art. 12) | Audit-Log je Anfrage ([audit-log.md](audit-log.md)) |
| Datenqualität | DQ-Regeln im Warehouse (`mart_data_quality_findings`), Datenverträge |
