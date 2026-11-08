# Planwerk

**Controlling- und Planungsplattform auf SAP-S/4HANA-Datenstrukturen, mit einem KI-Controlling-Assistenten,
dessen Zahlen einzeln geprüft werden.**

[English version](README.md) · [Ergebnisse](docs/ergebnisse/README.md) · [Lastenheft](docs/fachlich/lastenheft.md) · [Fachkonzept](docs/fachlich/fachkonzept.md)

> **Alle Unternehmensdaten sind simuliert.** Die Nordwerk GmbH ist ein fiktiver Pumpenhersteller mit
> drei Buchungskreisen (DE, AT, PL). Der Generator ist offen, reproduzierbar (Seed) und getestet.
> Real sind nur die makroökonomischen Treiber: Erzeugerpreise und Arbeitskosten (Eurostat/Destatis),
> EZB-Wechselkurse und Strompreise (SMARD).

## Drei Fragen, vorab festgelegt

Die Fragen, Messgrößen und Schwellenwerte stehen in [ADR-0001](docs/adr/0001-business-questions-and-hypotheses.md)
und wurden vor der ersten Auswertung festgelegt.

| | Frage | Ergebnis |
|---|---|---|
| Q1 | Woraus besteht die Lücke von 4,5 Mio. EUR im DB II gegenüber Plan (Preis, Menge, Mix, Kosten; welche Kostenstelle)? | Die Abweichungsbrücke schließt auf den Cent, 100 % der Kostenabweichung liegen auf benannten Kostenstellen. Von vier eingespielten Effekten werden drei innerhalb der Toleranz wiedergefunden, der Mengeneffekt nicht. **H1 nicht erfüllt.** |
| Q2 | Wie viele Monate früher erkennt ein rollierender ML-Forecast eine Zielverfehlung als die lineare Hochrechnung? | Über 200 simulierte Szenarien: Vorsprung im Median 0 Monate (Ziel 2). Der ML-Forecast hat keine Fehlalarme, die lineare Hochrechnung 11,3 %. **H2 nicht erfüllt.** |
| Q3 | Schreibt eine KI den deutschen Monatskommentar mit 100 % korrekten Zahlen und halbiert sie die Schreibzeit? | 39 von 39 Kommentaren mit ausschließlich korrekten Zahlen, auch mit einem absichtlich feindlichen Modell; 200 von 200 Fragen im Golden Set; 0 von 80 Angriffen erfolgreich. Die Zeitersparnis braucht einen praktizierenden Controller: **offen.** |

Negative Ergebnisse werden als negativ berichtet, Schwellen wurden nicht verschoben.

## Inhalt

- **Datengenerator** (`src/planwerk/generator`): S/4HANA-Tabellen (ACDOCA, ACDOCP, BKPF/BSEG, VBAK/VBAP,
  VBRK/VBRP, EKKO/EKPO, AFKO, MARA/MARC/MBEW, KNA1, LFA1, CSKS u. a.), rund 2,4 Mio. Buchungszeilen
  über 36 Monate, mit Ground-Truth-Manifest der eingespielten Effekte.
- **Data Warehouse** (`dbt`): DuckDB lokal, auf Snowflake übertragbar. Kimball-Modell, SCD2 für
  Kostenstellen, Datenverträge, Zeilenberechtigung je Kostenstellenverantwortlichem.
- **Controlling-Logik**: BAB mit Umlage, Deckungsbeitragsrechnung DB I bis III, Preis-Mengen-Mix-Abweichung,
  Kostenabweichung je Kostenstelle und Kostenart, GuV nach Gesamtkostenverfahren (HGB § 275 Abs. 2) mit
  Überleitung, 13-Wochen-Liquiditätsvorschau.
- **Forecast**: rollierend 3+9, 6+6, 9+3; lineare Hochrechnung, saisonal naiv und Gradient Boosting mit
  Auftragseingang als Frühindikator; Backtest über 200 Szenarien ohne Datenleck.
- **Berichte**: Monatsbericht in Excel (DB-Rechnung, Abweichungsbrücke, Produktgruppen, Kostenstellen,
  XVERWEIS, Power-Query-Anleitung) und Lenkungskreis-Präsentation (python-pptx, native Diagramme).
- **SAC Planning**: Importdateien und Modellentwurf für die treiberbasierte Planung 2026 (`sac`).
- **KI-Assistent**: feste Auswertungsarten, nur lesendes SQL auf semantischen Sichten, Zahlen nur über
  Platzhalter, Prüfer für jede Zahl; LangGraph, Azure OpenAI (EU) oder Offline-Modus, MCP-Server,
  Schutz gegen Prompt-Injection, Audit-Log.
- **Governance**: Berechtigungskonzept, Verzeichnis der Verarbeitungstätigkeiten, DSFA, Einordnung nach
  EU AI Act, Kontrollmatrix nach ISO-27001-Muster.
- **Betrieb**: Terraform für Snowflake und Azure mit Kostenobergrenzen, GitHub Actions mit OIDC, Runbook.

## Ausführen

```bash
make install generate dbt
make forecast backtest liquidity q1 eval reports
```

Die Ergebnisse liegen danach in `reports/out/` und `docs/ergebnisse/`. Details stehen im [Runbook](docs/betrieb/runbook.md).

## Noch offen

SAP HANA Cloud, Datasphere, CAP-Service auf BTP und SAC-Story brauchen SAP-Testzugänge. Snowflake- und
Azure-Läufe brauchen Konten. Teams-Anbindung, Power-Automate-Freigabe und RAG über Azure AI Search sind
geplant. Für die Zeitmessung (Q3) und die Umsetzung auf echten Daten wird ein Pilotunternehmen gesucht
([docs/outreach](docs/outreach)).
