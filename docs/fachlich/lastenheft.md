# Lastenheft Planwerk

**Controlling- und Planungsplattform mit KI-Controlling-Assistent für die Nordwerk-Gruppe**

| | |
|---|---|
| Auftraggeber | Nordwerk GmbH, Bremen (Leitung Finanzen und Controlling) |
| Auftragnehmer | Parsa Kamali |
| Version | 1.0 vom 07.11.2026 |
| Status | Abgestimmt im Kick-off (simuliert) |
| Hinweis | **Nordwerk GmbH ist ein fiktives Unternehmen.** Alle Unternehmensdaten sind simuliert (Track B, siehe ADR-0002). Real sind nur die makroökonomischen Treiber (Eurostat/Destatis, EZB, SMARD). |

---

## 1 Ausgangssituation

Die Nordwerk-Gruppe stellt Kreiselpumpen, Dosierpumpen, Ventile und Armaturen her und
erbringt Service- und Ersatzteilgeschäft. Sie besteht aus drei Buchungskreisen:

| Buchungskreis | Gesellschaft | Land | Währung | Umsatzanteil |
|---|---|---|---|---|
| 1000 | Nordwerk GmbH | DE | EUR | ca. 70 % |
| 2000 | Nordwerk Austria GmbH | AT | EUR | ca. 12 % |
| 3000 | Nordwerk Polska Sp. z o.o. | PL | PLN | ca. 18 % |

Die Gruppe erzielt rund 250 Mio. EUR Umsatz mit etwa 1.100 Beschäftigten. Das ERP-System ist
SAP S/4HANA (Universal Journal ACDOCA, Planung in ACDOCP).

**Probleme heute (Ist-Zustand):**

1. Der Monatsbericht wird in Excel aus mehreren SAP-Exporten manuell zusammengebaut. Er ist
   frühestens am 8. Arbeitstag fertig und hängt an einer Person.
2. Die Plan-Ist-Abweichung im Deckungsbeitrag wird nur als Gesamtzahl gezeigt. Ob sie aus Preis,
   Menge, Mix oder Kosten kommt, wird jedes Mal neu von Hand geschätzt.
3. Die Hochrechnung ist linear (Ist bis Monat × 12 / Monat). Sie ignoriert Saisonalität und
   Auftragsbestand und meldet Zielverfehlungen zu spät oder falsch.
4. Der Monatskommentar für die Geschäftsführung kostet den Controller pro Monat ca. 1,5 Tage.
5. Es gibt keine dokumentierte Datenherkunft, kein Berechtigungskonzept für
   Kostenstellenverantwortliche und keine Prüfung der Stammdatenqualität.

## 2 Zielsetzung

Planwerk soll Controlling und Planung auf eine einheitliche, geprüfte Datenbasis stellen und
drei fachliche Fragen belastbar beantworten (verbindlich festgelegt in ADR-0001):

| Nr. | Fachliche Frage | Messgröße |
|---|---|---|
| F1 | Woraus setzt sich die Plan-Ist-Abweichung im DB II zusammen (Preis, Menge, Mix, Kosten, Währung), und welcher Anteil entfällt auf welche Kostenstelle? | Zerlegung ohne Rest; ≥ 90 % der Kostenabweichung benannten Kostenstellen zugeordnet |
| F2 | Wie viele Monate früher erkennt ein rollierender ML-Forecast eine Zielverfehlung als die lineare Hochrechnung? | Median-Vorlauf ≥ 2 Monate bei nicht höherer Fehlalarmquote |
| F3 | Kann eine KI den Monatskommentar auf Deutsch mit 100 % korrekten Zahlen schreiben und ≥ 50 % Zeit sparen? | 100 % Zahlenkorrektheit auf festem Testset; ≥ 95 % Genauigkeit im Golden Set |

## 3 Funktionale Anforderungen

Priorität: **M** = Muss, **S** = Soll, **K** = Kann.

### 3.1 Datenbasis und Datenqualität

| ID | Anforderung | Prio |
|---|---|---|
| LA-01 | Übernahme der S/4HANA-Tabellen ACDOCA, ACDOCP, BKPF/BSEG, CSKS, SKA1, MARA/MARC/MBEW, VBAK/VBAP, VBRK/VBRP, EKKO/EKPO, KNA1/KNVV, LFA1 für 36 Monate (01/2023 bis 12/2025) | M |
| LA-02 | Kostenstellen mit Historie (Verantwortlicher, Profit-Center-Zuordnung zum jeweiligen Stichtag) | M |
| LA-03 | Automatische Prüfungen bei jeder Beladung: Belege ausgeglichen, Konten und Kostenstellen gültig, Referenzen vollständig; bei Fehlern keine Freigabe der Berichte | M |
| LA-04 | Stammdatenprüfungen im Stil von SAP MDG: fehlende USt-IdNr., Dubletten bei Kunden, ungültige Kostenstellen | M |
| LA-05 | Datenverträge (Schema, Pflichtfelder, Wertebereiche) für alle Quelltabellen | S |
| LA-06 | Herkunft jeder Kennzahl nachvollziehbar (Lineage bis zur Quelltabelle) | S |

### 3.2 Controlling-Logik

| ID | Anforderung | Prio |
|---|---|---|
| LA-10 | Betriebsabrechnungsbogen (BAB) mit Umlage der Hilfskostenstellen Energie, Instandhaltung und IT im Stufenleiterverfahren | M |
| LA-11 | Mehrstufige Deckungsbeitragsrechnung DB I bis DB III und Betriebsergebnis nach Produktgruppe, Kundengruppe und Buchungskreis | M |
| LA-12 | Plan-Ist-Vergleich und Abweichungsanalyse nach Preis, Menge, Mix, variablen Kosten, Fixkosten und Währung (PVM) | M |
| LA-13 | Rollierender Forecast in den Varianten 3+9, 6+6 und 9+3 | M |
| LA-14 | 13-Wochen-Liquiditätsvorschau aus offenen Posten, Zahlungsverhalten und wiederkehrenden Auszahlungen | M |
| LA-15 | Überleitung in die Gewinn- und Verlustrechnung nach § 275 Abs. 2 HGB (Gesamtkostenverfahren) | M |
| LA-16 | Konzernsicht in EUR mit Umrechnung PLN zu EZB-Monatsdurchschnittskursen | M |

### 3.3 Planung

| ID | Anforderung | Prio |
|---|---|---|
| LA-20 | Treiberbasierte Planung: Absatzmenge, Preis, Materialkosten je Einheit, Personal je Kostenstelle, Energiepreis, Wechselkurs | M |
| LA-21 | Planversionen (Budget, Forecast, Szenarien) mit Freigabestatus | M |
| LA-22 | Umsetzung in SAP Analytics Cloud Planning (Datenaktionen, Versionen); alternativ Jedox | S |
| LA-23 | Szenariorechnung „Was wäre, wenn" für Preis, Menge und Energiepreis | S |

### 3.4 Berichtswesen

| ID | Anforderung | Prio |
|---|---|---|
| LA-30 | Monatsbericht in Excel (deutsch) mit Plan-Ist-Vergleich, Abweichungsanalyse, Kostenstellenbericht, Forecast; Formeln mit XVERWEIS, Pivot und Power Query | M |
| LA-31 | Folien für den Lenkungskreis und die Geschäftsführung (PowerPoint, automatisch erzeugt) | M |
| LA-32 | Bericht je Kostenstellenverantwortlichem, der nur seine Kostenstellen zeigt | M |
| LA-33 | Bericht spätestens am 3. Arbeitstag nach Monatsabschluss verfügbar | S |

### 3.5 KI-Controlling-Assistent

| ID | Anforderung | Prio |
|---|---|---|
| LA-40 | Beantwortung von Controlling-Fragen in deutscher Sprache auf Basis der freigegebenen Kennzahlen | M |
| LA-41 | Alle Zahlen kommen aus geprüften SQL-Abfragen auf semantischen Sichten, nie aus dem Sprachmodell selbst | M |
| LA-42 | Entwurf des Monatskommentars je Buchungskreis mit automatischer Zahlenprüfung | M |
| LA-43 | Nur lesender Zugriff; jede Antwort nennt die Quelle (Sicht, Filter, Stand) | M |
| LA-44 | Bereitstellung als MCP-Server und in Microsoft Teams (Copilot Studio); Freigabe des Kommentars per Power Automate | S |
| LA-45 | Suche in Richtlinien und Fachkonzept (RAG) | K |

## 4 Nichtfunktionale Anforderungen

| ID | Anforderung | Prio |
|---|---|---|
| LN-01 | **Datenschutz (DSGVO):** keine Personaldaten auf Mitarbeiterebene; Personalkosten nur je Kostenstelle; Verzeichnis der Verarbeitungstätigkeiten und Datenschutz-Folgenabschätzung für den KI-Assistenten | M |
| LN-02 | **Berechtigungen:** Zeilenbasierte Berechtigung je Kostenstellenverantwortlichem; Rollen Controller, Kostenstellenverantwortlicher, Geschäftsführung, Administrator | M |
| LN-03 | **KI-Regulierung:** Einstufung nach EU AI Act; Transparenzhinweis bei KI-generierten Texten; menschliche Freigabe vor Versand | M |
| LN-04 | **Informationssicherheit:** Maßnahmen angelehnt an ISO 27001 Anhang A; Protokollierung aller Zugriffe des Assistenten | M |
| LN-05 | **Reproduzierbarkeit:** Infrastruktur als Code (Terraform), Pipelines in GitHub Actions mit OIDC, keine statischen Zugangsdaten im Repository | M |
| LN-06 | **Kostenkontrolle:** Kostenobergrenze für Cloud-Ressourcen und je KI-Antwort | M |
| LN-07 | **Qualitätssicherung:** automatisierte Tests für Daten, Logik und KI-Antworten in der CI | M |
| LN-08 | **Sprache:** Oberflächen, Berichte und Dokumentation für Anwender auf Deutsch | M |
| LN-09 | **Betrieb:** Betriebshandbuch (Runbook) mit Wiederanlauf und Eskalation | S |

## 5 Mengengerüst

| Objekt | Menge |
|---|---|
| Buchungskreise | 3 |
| Kostenstellen | 32 (davon 6 Hilfskostenstellen) |
| Materialien | ca. 500 (115 Fertigerzeugnisse, 300 Ersatzteile, 75 Komponenten, 4 Dienstleistungen) |
| Kunden | ca. 1.400 |
| Buchungszeilen ACDOCA | ca. 2,4 Mio. (Profil dev) bis ca. 35 Mio. (Profil full) für 36 Monate |
| Nutzer | ca. 35 (5 Controller, 25 Kostenstellenverantwortliche, 5 Geschäftsführung) |

## 6 Rahmenbedingungen

- Vorgehen nach Scrum mit zweiwöchigen Sprints, Sprint-Review mit dem Auftraggeber, Definition of Done
  (siehe `docs/projekt/definition-of-done.md`).
- Laufzeit 12 Wochen; Abnahme im Lenkungskreis in Woche 12.
- Testzugänge (SAP BTP, Snowflake, Azure) werden erst gebucht, wenn die jeweilige Schicht umgesetzt wird.
- Alle Ergebnisse sind als simuliert gekennzeichnet und werden anonymisiert veröffentlicht.

## 7 Abnahmekriterien

| Nr. | Kriterium |
|---|---|
| AK-1 | Alle Muss-Anforderungen umgesetzt und im Sprint-Review gezeigt |
| AK-2 | Datentests grün: 100 % der Belege ausgeglichen, keine ungültigen Kostenstellen |
| AK-3 | F1: Abweichungszerlegung schließt auf den Cent; injizierte Effekte innerhalb ± 10 % wiedergefunden |
| AK-4 | F2: Backtest über ≥ 200 Szenarien dokumentiert, Ergebnis gegen die Schwelle aus ADR-0001 berichtet (auch wenn negativ) |
| AK-5 | F3: 100 % Zahlenkorrektheit im Kommentar-Testset; ≥ 95 % im Golden Set; 0 erfolgreiche Prompt-Injection-Versuche |
| AK-6 | Governance-Dokumente vorhanden: Berechtigungskonzept, VVT, DSFA, AI-Act-Einstufung, Kontrollmatrix |
| AK-7 | Schulung der Key User durchgeführt, Abnahmeprotokoll unterschrieben |

## 8 Lieferumfang

1. Quellcode im Git-Repository (Generator, dbt-Projekt, Controlling-Logik, Forecast, KI-Assistent, Infrastruktur)
2. Pflichtenheft/Fachkonzept, Lastenheft, Architekturentscheidungen (ADR)
3. Excel-Monatsbericht und Lenkungskreis-Präsentation
4. Governance-Dokumente und Betriebshandbuch
5. Schulungsunterlagen und Abnahmeprotokoll
