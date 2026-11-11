# SAP Analytics Cloud: Planungsmodell NW_CONTROLLING

> Simulierte Daten (Nordwerk GmbH). Die Importdateien erzeugt `python -m planwerk.sac.export`
> (Ordner `sac/import/`, Abgleich mit dem Warehouse im Test `tests/test_sac_export.py`).
> Für den Aufbau im SAC-Tenant wird ein Trial benötigt (siehe Liste „Was Sie selbst tun müssen“).

## 1. Modelle

| Modell | Typ | Zweck |
|---|---|---|
| `NW_CONTROLLING` | Planungsmodell (Kennzahlenmodell mit Measures) | Ist, Budget, Forecast der DB-Rechnung je Gesellschaft, Produktgruppe, Kostenstelle |
| `NW_SALES_DRIVERS` | Planungsmodell | Treiber je Gesellschaft × Produktgruppe × Monat: Menge, Nettopreis, Standardkosten |

### Dimensionen `NW_CONTROLLING`

| Dimension | Typ | Datei | Hierarchie |
|---|---|---|---|
| Version | Version | `dim_version.csv` | Actual, Budget2023–2026, FC3_9/FC6_6/FC9_3_2025 |
| Date | Datum (Monat) | – | Jahr > Quartal > Monat |
| Account | Konto | `dim_account.csv` | BE > DB III > DB II > DB I > Nettoumsatz/variable Kosten; Fixkostenkonten unter `FIX_COSTS` |
| Entity | Organisation | `dim_entity.csv` | GRUPPE > 1000 DE, 2000 AT, 3000 PL (Währung je Gesellschaft) |
| ProductGroup | generisch | `dim_productgroup.csv` | ALL_PG > PG10…PG50, `#` |
| CostCenter | generisch | `dim_costcenter.csv` | ALL_CC > DB-Stufe (CM_DB2/CM_DB3/CM_UNT/CM_HILF) > Kostenstelle; Attribut `Responsible` für Datenzugriffssteuerung |

Measures: `Amount_EUR` (Konzernwährung), `Quantity`. Die Zuordnung der Fixkosten zu DB II, DB III und
Unternehmensfixkosten ergibt sich aus der DB-Stufe der Kostenstelle; berechnete Konten
`FIX_DB2 = [FIX_COSTS] für CostCenter-Knoten CM_DB2` usw.

### Datenzugriffssteuerung
CostCenter mit „Data Access Control“: Lese-/Schreibrechte je Kostenstellenverantwortlichem
(Attribut `Responsible`), entspricht `cost_centre_access.csv`. Controlling: Schreiben auf allen Knoten.
Stand 2026-11-11: In der öffentlichen Dimension `NW_COSTCENTER` ist `Responsible` leer, weil SAC dort
SAC-Benutzer-IDs erwartet (Import-Fehler „INVALID_USER_ID“). Die Einschränkung je Kostenstelle ist in
SAP Datasphere umgesetzt (`DAC_COSTCENTER` auf `V_COST_BY_CC`, siehe `docs/ergebnisse/README.md`).

## 2. Datenaktionen

### DA_01 Ist in Forecast kopieren (Rolling Forecast)
Kopiert geschlossene Monate von `Actual` in die Forecast-Version, z. B. 6+6: Januar–Juni.

```
MEMBERSET [d/Date] = "202501" TO "202506"
DATA() = RESULTLOOKUP([d/Version] = "public.Actual")
```

Die Zielversion (`public.FC6_6_2025`) wird beim Ausführen gewählt. Die erste Fassung mit
`DATA([d/Version] = ...)` lehnte SAC ab („The version dimension cannot be used in the left operand“).
Getestet am 2026-11-11: 1.770 Zeilen, 234.991.696,03 EUR = Ist Januar–Juni 2025.

### DA_02 Treiberbasierte Umsatz- und Materialplanung (aus `NW_SALES_DRIVERS`)
Plan-Umsatz = Menge × Nettopreis, variable Kosten = Menge × Standardkosten, je Gesellschaft,
Produktgruppe und Monat. Startwerte: `driver_basis_2026.csv` (Ist 2025).

Erste Fassung (2026-11-11, auf `NW_CONTROLLING`/`NW_SALES_DRIVERS` mit privaten Dimensionen):

```
MEMBERSET [d/Version] = "public.Budget2026"
MEMBERSET [d/Account] = ("ERL_PROD", "VAR_MAT")
DATA([d/Account] = "ERL_PROD") = LINK([NW_SALES_DRIVERS], [d/Measures] = "Units")
                                * LINK([NW_SALES_DRIVERS], [d/Measures] = "Price_EUR")
DATA([d/Account] = "VAR_MAT")  = LINK([NW_SALES_DRIVERS], [d/Measures] = "Units")
                                * LINK([NW_SALES_DRIVERS], [d/Measures] = "StdCost_EUR")
```

Nicht lauffähig: SAC verlangt, dass „ProductGroup, Entity, Version“ für `NW_SALES_DRIVERS` angegeben
werden, weil beide Modelle eigene (private) Dimensionen haben.

Lauffähige Fassung (2026-11-11, zweiter Lauf) auf `NW_CONTROLLING_V2` und `NW_SALES_DRIVERS_V2`.
Beide Modelle nutzen die öffentlichen Dimensionen `NW_ENTITY` und `NW_PRODUCTGROUP` und eine
Datumsdimension mit derselben ID (`Monat`). Die Zielversion `Budget2026` wird beim Ausführen gewählt:

```
MEMBERSET [d/Monat] = "202601" TO "202612"
MEMBERSET [d/Measures] = "Amount_EUR"
DATA([d/Account] = "ERL_PROD", [d/CostCenter] = "#") =
    LINK([NW_SALES_DRIVERS_V2], [d/Measures] = "Units", [d/Version] = "public.Budget2026",
         [d/Entity] = [d/Entity], [d/ProductGroup] = [d/ProductGroup])
  * LINK([NW_SALES_DRIVERS_V2], [d/Measures] = "Price_EUR", [d/Version] = "public.Budget2026",
         [d/Entity] = [d/Entity], [d/ProductGroup] = [d/ProductGroup])
DATA([d/Account] = "VAR_MAT", [d/CostCenter] = "#") =
    LINK([NW_SALES_DRIVERS_V2], [d/Measures] = "Units", [d/Version] = "public.Budget2026",
         [d/Entity] = [d/Entity], [d/ProductGroup] = [d/ProductGroup])
  * LINK([NW_SALES_DRIVERS_V2], [d/Measures] = "StdCost_EUR", [d/Version] = "public.Budget2026",
         [d/Entity] = [d/Entity], [d/ProductGroup] = [d/ProductGroup])
```

(Im Tenant steht jede `DATA`-Anweisung in einer Zeile.) Auch mit öffentlichen Dimensionen verlangte
SAC weiter „Version, Entity, ProductGroup“; `[d/Version] = [d/Version]` ergab „Reference version name
should be specified“. Ergebnis: Budget 2026 ERL_PROD 237.043.778,99 EUR, VAR_MAT 101.544.395,93 EUR,
je 144 Zeilen, gleich Σ Menge × Preis bzw. Σ Menge × Standardkosten aus `driver_basis_2026.csv`.
Die Fakten in `NW_CONTROLLING_V2` sind mit Vorzeichenumkehr nach Kontotyp importiert, damit die
Hierarchie DB I richtig verdichtet; das Skript braucht dann keine eigene Vorzeichenbehandlung
(`CONFIG.FLIPPING_SIGN_ACCORDING_ACCTYPE = ON` oder `-1 *` lieferten den Umsatz mit falschem Vorzeichen).

### DA_03 Preis- und Mengenannahmen
Eingabe-Story mit Prozent-Treibern je Produktgruppe (Preiserhöhung, Mengenwachstum), angewendet auf
die Startwerte: `Price_EUR = Price_EUR * (1 + [Preiserhöhung])`, `Units = Units * (1 + [Mengenwachstum])`.
Diese Treiber entsprechen den Generator-Parametern `PRICE_INCREASE` und `YEAR_VOLUME` (Fachkonzept, Anhang A).

### DA_04 Skonto-Planung
`ERL_SKONTO = ERL_PROD × Skontoquote` je Gesellschaft (Quote aus Ist der letzten 12 Monate).

### DA_05 BAB-Umlage (Allocation Process)
Stufenleiterverfahren wie im Warehouse (`dbt/seeds/bab_cycle.csv`, Modell `int_bab_allocation`):
Energie → Instandhaltung → Fertigung/Vertrieb nach Umlageschlüsseln (`ALLOC_KEYS`). In SAC als
Allocation Step je Stufe mit Treiber „Schlüsselanteil“.

### DA_06 Version freigeben
Veröffentlichen der privaten Version nach Freigabe durch die Geschäftsführung (Kalender-Aufgabe
„Budget 2026 – Freigabe“).

## 3. Planungskalender Budget 2026 (Vorschlag)

| Woche | Schritt | Verantwortlich |
|---|---|---|
| 1 | Startwerte laden (DA_02 mit Ist 2025), Annahmen-Story freischalten | Controlling |
| 2–3 | Preis- und Mengenannahmen je Produktgruppe | Vertrieb |
| 3–4 | Kostenstellenbudgets (Fixkosten je Konto) | Kostenstellenverantwortliche |
| 5 | Umlage (DA_05), Konsolidierung, Plausibilisierung gegen Forecast 9+3 | Controlling |
| 6 | Freigabe (DA_06) | Geschäftsführung |

## 4. Import (Schritte im Tenant)

1. Dimensionen anlegen und je Datei importieren (Spalten `ID`, `Description`, `ParentId`, ggf. `Currency`/`Responsible`).
2. Modell `NW_CONTROLLING` anlegen, Fakten `fact_ist_plan.csv` importieren (Mapping 1:1, Trennzeichen `;`).
3. Modell `NW_SALES_DRIVERS` mit `driver_basis_2026.csv` befüllen.
4. Datenaktionen DA_01–DA_06 anlegen, Story „Monatsbericht“ und „Budget 2026 Eingabe“ bauen.
5. Abgleich: DB I und Fixkosten je Version/Jahr müssen den Werten in `controlling.mart_db_statement_monthly`
   entsprechen (dieselbe Prüfung wie `tests/test_sac_export.py`).

Alternative ohne SAC-Tenant: dieselben Treiberlogiken laufen in Jedox oder Excel; die Importdateien sind
werkzeugneutral.
