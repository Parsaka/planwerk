// Planwerk controlling model for SAP HANA Cloud (HDI) and the CAP service.
// Mirrors the dbt semantic views (schema SEMANTIC); the same column names, German business terms.
// All figures are SIMULATED (fictional Nordwerk GmbH).
namespace planwerk;

type Bereich    : String(10) @title: 'Bereich (GRUPPE oder Buchungskreis)';
type BetragEUR  : Decimal(17, 2);

@title: 'Kennzahlen je Monat (Ist, Plan, Abweichung)'
entity KennzahlenMonat {
  key periode        : String(7);
  key bereich        : Bereich;
  key kennzahl       : String(40);
      jahr           : Integer;
      monat          : Integer;
      ist_eur        : BetragEUR;
      plan_eur       : BetragEUR;
      abweichung_eur : BetragEUR;
      abweichung_pct : Decimal(9, 6);
}

@title: 'Abweichungsbrücke DB II Plan -> Ist (kumuliert)'
entity Abweichungsbruecke {
  key jahr                      : Integer;
  key bis_monat                 : Integer;
  key bereich                   : Bereich;
      plan_db2_eur              : BetragEUR;
      mengeneffekt_eur          : BetragEUR;
      mixeffekt_eur             : BetragEUR;
      preiseffekt_eur           : BetragEUR;
      materialkosteneffekt_eur  : BetragEUR;
      erloesschmaelerung_eur    : BetragEUR;
      fixkosteneffekt_db2_eur   : BetragEUR;
      waehrungseffekt_eur       : BetragEUR;
      ist_db2_eur               : BetragEUR;
      plan_betriebsergebnis_eur : BetragEUR;
      ist_betriebsergebnis_eur  : BetragEUR;
}

@title: 'Kostenstellen Plan/Ist (kumuliert)'
entity Kostenstellen {
  key jahr              : Integer;
  key bis_monat         : Integer;
  key bereich           : Bereich;
  key kostenstelle      : String(10);
      kostenstelle_text : String(60);
      verantwortlich    : String(60);
      plan_eur          : BetragEUR;
      ist_eur           : BetragEUR;
      abweichung_eur    : BetragEUR;
}

@title: 'Kostenarten je Kostenstelle Plan/Ist (kumuliert)'
entity Kostenarten {
  key jahr              : Integer;
  key bis_monat         : Integer;
  key bereich           : Bereich;
  key kostenstelle      : String(10);
  key konto             : String(10);
      kostenstelle_text : String(60);
      konto_text        : String(60);
      plan_eur          : BetragEUR;
      ist_eur           : BetragEUR;
      abweichung_eur    : BetragEUR;
}

@title: 'Produktgruppen mit Preis-, Mengen-, Mix- und Materialkosteneffekt'
entity Produktgruppen {
  key jahr                     : Integer;
  key bis_monat                : Integer;
  key bereich                  : Bereich;
  key produktgruppe            : String(10);
      produktgruppe_text       : String(60);
      ist_umsatz_eur           : BetragEUR;
      plan_umsatz_eur          : BetragEUR;
      ist_db1_eur              : BetragEUR;
      plan_db1_eur             : BetragEUR;
      preiseffekt_eur          : BetragEUR;
      mengeneffekt_eur         : BetragEUR;
      mixeffekt_eur            : BetragEUR;
      materialkosteneffekt_eur : BetragEUR;
}

@title: 'Auftragseingang und Umsatz je Monat'
entity Auftragseingang {
  key periode             : String(7);
  key bereich             : Bereich;
  key produktgruppe       : String(10);
      jahr                : Integer;
      monat               : Integer;
      auftragseingang_eur : BetragEUR;
      umsatz_eur          : BetragEUR;
}
