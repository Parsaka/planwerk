# Zeitmessprotokoll Monatskommentar (Q3, Kriterium 3)

**Status: offen.** Ohne praktizierenden Controller lässt sich die Zeitersparnis nicht ehrlich messen.
Dieses Protokoll ist vorab festgelegt (ADR-0001) und wird im ersten Kundenprojekt (Track A) durchgeführt.

## Design

* **Teilnehmende:** mindestens ein praktizierender Controller (besser drei), mit Erfahrung im Monatsbericht.
* **Aufgaben:** 6 Monatskommentare aus dem festen Testset (`eval/commentary_testset.yaml`), zufällig je
  Person auf zwei Bedingungen verteilt (Within-Subject, Reihenfolge ausbalanciert):
  * **A – manuell:** Controller schreibt den Kommentar mit dem Excel-Monatsbericht als Grundlage.
  * **B – mit Assistent:** Controller erhält den Entwurf des Assistenten und überarbeitet ihn bis zur Freigabe.
* **Gemessen:** Zeit vom Öffnen der Unterlagen bis zur Freigabe (Stoppuhr, selbst protokolliert),
  Anzahl inhaltlicher Korrekturen in B, Qualitätsurteil eines zweiten Controllers (blind, Skala 1–5).
* **Auswertung:** Median der relativen Zeitersparnis je Kommentarpaar. Kriterium erfüllt, wenn
  Median ≥ 50 % **und** das blinde Qualitätsurteil für B nicht schlechter ist als für A (Differenz ≥ −0,5).
* **Bericht:** Rohdaten und Auswertung in `docs/ergebnisse/q3_zeitmessung.md`, auch wenn das Kriterium verfehlt wird.

## Vorlage Rohdaten

| Person | Kommentar-ID | Bedingung | Minuten | Korrekturen | Qualitätsurteil (blind) |
|---|---|---|---|---|---|
| | | | | | |
