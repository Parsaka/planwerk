# Verzeichnis von Verarbeitungstätigkeiten (Art. 30 Abs. 1 DSGVO), Auszug Planwerk

> **Hinweis:** Planwerk verarbeitet im Portfolio-Betrieb ausschließlich **simulierte Daten** der fiktiven
> Nordwerk GmbH. Dieses Verzeichnis ist so geschrieben, dass es beim Einsatz mit echten Daten eines
> Kunden (Track A) als Vorlage dient; Platzhalter in spitzen Klammern sind dann zu füllen.

| | |
|---|---|
| Verantwortlicher | `<Kunde>`, vertreten durch die Geschäftsführung |
| Datenschutzbeauftragte/r | `<Name, Kontakt>` |
| Stand | 2026-11-08, Version 1.0 |

## Nr. 1 – Controlling-Datenhaltung und Berichtswesen

| Merkmal | Beschreibung |
|---|---|
| Zweck | Plan/Ist-Vergleich, Deckungsbeitragsrechnung, Kostenstellenrechnung, Forecast, Liquiditätsplanung, Monatsberichte |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. c DSGVO (handels- und steuerrechtliche Pflichten, §§ 238 ff. HGB) und lit. f (berechtigtes Interesse an Unternehmenssteuerung) |
| Betroffene | Ansprechpartner von Kunden und Lieferanten (B2B), Beschäftigte nur aggregiert über Kostenstellen |
| Datenkategorien | Firmen-Stammdaten, ggf. Ansprechpartnernamen (KNA1/LFA1), Buchungsbelege, Kostenstellenverantwortliche (Name/Funktion). **Keine** Einzelgehälter: Personalkosten nur als Summe je Kostenstelle und Konto |
| Empfänger | Controlling, Geschäftsführung, Kostenstellenverantwortliche (eigene Kostenstellen) |
| Auftragsverarbeiter | Snowflake (Region EU), Microsoft Azure (EU), SAP BTP (EU) – jeweils AVV nach Art. 28 DSGVO |
| Drittlandtransfer | Keiner geplant; Regionen EU. Falls Support-Zugriffe aus Drittländern: EU-US Data Privacy Framework bzw. SCC des Anbieters |
| Löschfristen | Buchungsdaten 10 Jahre (§ 257 HGB, § 147 AO), Berichte 6 Jahre, Staging-/Arbeitstabellen bei jedem Lauf neu |
| TOM | siehe [Kontrollmatrix](kontrollmatrix.md): Rollen und Zeilenberechtigung, Verschlüsselung at rest/in transit, Protokollierung, Backup/Time Travel |

## Nr. 2 – KI-Controlling-Assistent

| Merkmal | Beschreibung |
|---|---|
| Zweck | Beantwortung von Controlling-Fragen und Entwurf des Monatskommentars auf Basis freigegebener Kennzahlen |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. f DSGVO (effiziente Berichterstellung); für Beschäftigtendaten § 26 BDSG nur im Rahmen der Nutzerverwaltung |
| Betroffene | Nutzer des Assistenten (Beschäftigte) |
| Datenkategorien | Benutzerkennung, Rolle, Fragetext, Zeitstempel, Verbrauch (Audit-Log); die Antworten enthalten nur aggregierte Kennzahlen |
| Empfänger | Plattform-Owner (Betrieb), Datenschutz (auf Anfrage) |
| Auftragsverarbeiter | Microsoft (Azure OpenAI, Data Zone EU, keine Verwendung der Eingaben zum Modelltraining laut Produktbedingungen, Abuse-Monitoring gemäß Microsoft-Bedingungen) |
| Löschfristen | Audit-Log 12 Monate |
| Besonderheiten | Keine automatisierte Einzelentscheidung (Art. 22 DSGVO): der Assistent liefert Berichtstexte, Entscheidungen trifft der Mensch. Keine Leistungs- oder Verhaltenskontrolle von Beschäftigten über das Audit-Log (Mitbestimmung § 87 Abs. 1 Nr. 6 BetrVG beachten; Betriebsvereinbarung empfohlen) |

## Nr. 3 – Entwicklung und Test

| Merkmal | Beschreibung |
|---|---|
| Zweck | Entwicklung, CI-Tests, Evaluation |
| Datenkategorien | Ausschließlich simulierte Daten (Generator, Seed 42). Echte Daten werden nie in Test- oder CI-Umgebungen kopiert |
| Löschfristen | CI-Artefakte 90 Tage (GitHub-Standard) |
