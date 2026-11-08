# Definition of Done

Ein Backlog-Eintrag ist fertig, wenn **alle** Punkte erfüllt sind. Qualität vor Geschwindigkeit: lieber
ein Eintrag weniger im Sprint als ein Eintrag ohne Test.

## Für jeden Eintrag
- [ ] Akzeptanzkriterien aus dem Ticket erfüllt und im Sprint-Review gezeigt
- [ ] Code im Pull Request, Review durch eine zweite Person (bzw. Self-Review mit Checkliste bei Einzelarbeit)
- [ ] CI grün: `ruff`, `pytest`, `dbt build` mit allen Tests, Q3-Eval mit Exit-Code 0, `terraform validate`
- [ ] Keine Zugangsdaten im Code, keine Echtdaten in Test/CI
- [ ] Dokumentation aktualisiert (Fachkonzept, Runbook oder README, wo betroffen)

## Zusätzlich für Datenmodelle (dbt)
- [ ] Spalten beschrieben, Schlüssel mit `unique`/`not_null`, Beziehungen mit `relationships`
- [ ] Fachliche Identität als Test (z. B. Brücke schließt, Belege ausgeglichen, BAB vollständig verteilt)
- [ ] Marts mit Konsumenten (SAC, Assistent, Excel) haben einen erzwungenen Vertrag (`contract: enforced`)

## Zusätzlich für Controlling-Logik
- [ ] Ergebnis gegen die Ground Truth des Generators bzw. eine Handrechnung geprüft
- [ ] Vorzeichenkonvention dokumentiert (positiv = günstig)

## Zusätzlich für den KI-Assistenten
- [ ] Neue Fragetypen im Golden Set ergänzt (erwartete Werte als SQL, nicht von Hand)
- [ ] Verifier lässt keine Zahl außerhalb des Faktenblatts durch (Test mit feindlichem Modell)
- [ ] Injection-Suite unverändert bei 0 erfolgreichen Angriffen

## Für das Sprint-Ende
- [ ] Ergebnisse mit Status „erfüllt / verfehlt / offen“ in `docs/ergebnisse` festgehalten
- [ ] Offene Risiken und Annahmen im Sprint-Protokoll
