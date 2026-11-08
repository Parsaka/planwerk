"""Builds the frozen 200-question golden set (eval/golden_set.yaml).

Each item has a German question, the user who asks it, the expected intent or status, and
the expected figures as SQL. The SQL deliberately reads the controlling/core marts and the
forecast tables, *not* the semantic views the assistant uses, so a mapping error in the
semantic layer or in the assistant's queries is caught. Values are computed at eval time,
so the set is valid for any seed or profile.

Run once (seeded); the output is committed and must not be regenerated to tune results.
"""

from __future__ import annotations

import random
from pathlib import Path

import yaml

OUT = Path(__file__).with_name("golden_set.yaml")
rng = random.Random(20251231)

MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
SCOPE_SURF = {
    "GRUPPE": ["", "in der Gruppe", "im Konzern", "für die Gruppe gesamt"],
    "1000": ["in Deutschland", "für die Nordwerk GmbH", "DE", "im Buchungskreis 1000"],
    "2000": ["in Österreich", "für Nordwerk Austria", "AT", "im Buchungskreis 2000"],
    "3000": ["in Polen", "für Nordwerk Polska", "PL", "im Buchungskreis 3000"],
}
KPI_SURF = {
    "umsatz": ["der Umsatz", "die Umsatzerlöse"], "nettoumsatz": ["der Nettoumsatz", "die Nettoerlöse"],
    "variable_kosten": ["die variablen Kosten", "die Materialkosten"], "db1": ["der DB I", "der Deckungsbeitrag I"],
    "db2": ["der DB II", "der Deckungsbeitrag II", "der DB2"], "db3": ["der DB III", "der Deckungsbeitrag III"],
    "betriebsergebnis": ["das Betriebsergebnis", "das EBIT"],
    "unternehmensfixkosten": ["die Unternehmensfixkosten"], "fixkosten_db3": ["die Bereichsfixkosten"],
    "fixkosten_db2": ["die Fixkosten der Produktgruppen"],
}
KPI_COL = {"umsatz": "revenue_eur", "nettoumsatz": "net_revenue_eur", "variable_kosten": "var_cost_eur",
           "db1": "db1_eur", "fixkosten_db2": "fix_db2_eur", "db2": "db2_eur", "fixkosten_db3": "fix_db3_eur",
           "db3": "db3_eur", "unternehmensfixkosten": "fix_unt_eur", "betriebsergebnis": "operating_result_eur"}
KPI_WEIGHTS = {"umsatz": 4, "db2": 5, "db1": 3, "betriebsergebnis": 3, "variable_kosten": 2, "nettoumsatz": 1,
               "db3": 2, "unternehmensfixkosten": 1, "fixkosten_db3": 1, "fixkosten_db2": 1}
PG = {"PG10": ["Kreiselpumpen", "PG10"], "PG20": ["Dosierpumpen", "PG20"], "PG30": ["Ventile", "Armaturen", "PG30"],
      "PG40": ["Ersatzteile", "PG40"], "PG50": ["PG50"]}
EFFECT_SURF = {"preiseffekt": ["der Preiseffekt", "die Preisabweichung"], "mengeneffekt": ["der Mengeneffekt"],
               "mixeffekt": ["der Mixeffekt"], "materialkosteneffekt": ["der Materialkosteneffekt"]}
BRIDGE_EFFECT_COL = {"preiseffekt": "price_effect", "mengeneffekt": "volume_effect", "mixeffekt": "mix_effect",
                     "materialkosteneffekt": "var_cost_effect", "waehrungseffekt": "fx_effect_db2"}
PG_EFFECT_COL = {"preiseffekt": "price_effect", "mengeneffekt": "volume_effect", "mixeffekt": "mix_effect",
                 "materialkosteneffekt": "var_cost_effect"}
CC_NAMED = {"1620": "Marketing", "1530": "Qualitätssicherung", "1200": "Forschung und Entwicklung",
            "1610": "Vertrieb Export", "1300": "Einkauf und Materialwirtschaft"}
CC_ALL = ["1100", "1110", "1130", "1200", "1300", "1400", "1410", "1500", "1510", "1520", "1530", "1600", "1610",
          "1620", "1700", "1800", "2100", "2400", "2500", "2600", "2700", "2800", "3100", "3400", "3410", "3500",
          "3600", "3700", "3800"]


def pick(xs):
    return rng.choice(xs)


def scope_sql(scope: str, col: str = "company_code") -> str:
    return "" if scope == "GRUPPE" else f" and {col} = '{scope}'"


def clean(q: str) -> str:
    q = " ".join(q.split())
    return q.replace(" ?", "?").replace(" ,", ",").replace(" .", ".").replace(" :", ":")


items: list[dict] = []


def add(category, question, intent=None, status="answered", user="controller", expected=None, forbidden=None):
    items.append(dict(id=f"g{len(items) + 1:03d}", category=category, question=clean(question), user=user,
                      expected_intent=intent, expected_status=status, expected=expected or [],
                      forbidden_tokens=forbidden or []))


def kpi_expect(kpi, scope, year, m_from, m_to):
    col = KPI_COL[kpi]
    return [dict(name="ist_plan", sql=(
        f"select sum(case when version = 'IST' then {col} end) as ist_eur, "
        f"sum(case when version = 'PLAN' then {col} end) as plan_eur, "
        f"sum(case when version = 'IST' then {col} else -{col} end) as abweichung_eur "
        f"from controlling.mart_db_statement_monthly where fiscal_year = {year} "
        f"and fiscal_month between {m_from} and {m_to}{scope_sql(scope)}"))]


def verbs(surf: str) -> dict:
    pl = surf.startswith("die ")
    return dict(v="waren" if pl else "war", vi="sind" if pl else "ist", st="stehen" if pl else "steht",
                hat="haben" if pl else "hat", acc=("den " + surf[4:]) if surf.startswith("der ") else surf)


def weighted_kpi():
    return rng.choices(list(KPI_WEIGHTS), weights=list(KPI_WEIGHTS.values()))[0]


# 1) KPI for one month (45)
templates_m = ["Wie hoch {v} {k} {s} im {mon} {y}?", "Wie {hat} sich {k} im {mon} {y} {s} gegenüber dem Plan entwickelt?",
               "Plan-Ist-Vergleich: {K} {s}, {mon} {y}", "{K} {mon} {y} {s} – liegen wir im Plan?",
               "Zeig mir {acc} {s} für {y}-{mm}.", "Ist und Plan {kk} {s} im {mon} {y}?"]
for _ in range(45):
    kpi, scope, year = weighted_kpi(), pick(list(SCOPE_SURF)), pick([2025, 2025, 2025, 2024, 2023])
    m = rng.randint(1, 12)
    surf = pick(KPI_SURF[kpi])
    kk = surf.split(" ", 1)[1]
    q = pick(templates_m).format(k=surf, K=surf[0].upper() + surf[1:], kk=kk, s=pick(SCOPE_SURF[scope]),
                                 mon=MONTHS[m - 1], y=year, mm=f"{m:02d}", **verbs(surf))
    add("kpi_month", q, "kpi", expected=kpi_expect(kpi, scope, year, m, m))

# 2) KPI year to date (35)
templates_y = ["Wie hoch {vi} {k} {s} kumuliert bis {mon} {y}?", "{K} {s} seit Jahresbeginn bis {mon} {y}?",
               "{K} {s} YTD {mon} {y}", "Wo {st} {k} {s} im Gesamtjahr {y}?", "{K} {s} im {q}. Quartal {y} kumuliert?",
               "Wie hoch {v} {kp} {s} bis Ende {mon} {y}?"]
for _ in range(35):
    kpi, scope, year = weighted_kpi(), pick(list(SCOPE_SURF)), pick([2025, 2025, 2024, 2023])
    t = pick(templates_y)
    m = 12 if "Gesamtjahr" in t else rng.randint(2, 12)
    qn = rng.randint(1, 4)
    if "Quartal" in t:
        m = qn * 3
        t = "Wie hoch {v} {k} {s} kumuliert in Q{q} {y}?"
    surf = pick(KPI_SURF[kpi])
    q = t.format(k=surf, K=surf[0].upper() + surf[1:], kp=surf, s=pick(SCOPE_SURF[scope]), mon=MONTHS[m - 1], y=year,
                 q=qn, **verbs(surf))
    add("kpi_ytd", q, "kpi", expected=kpi_expect(kpi, scope, year, 1, m))

# 3) Budget bridge (20)
templates_b = ["Warum weicht der DB II {s} bis {mon} {y} vom Plan ab?", "Erkläre die Abweichung des DB II {s} bis {mon} {y}.",
               "Abweichungsbrücke DB II {s}, Januar bis {mon} {y}", "Was treibt die Planabweichung im DB II {s} bis {mon} {y}?",
               "Wie hoch ist {e} {s} bis {mon} {y}?"]
for _ in range(20):
    scope, year, m = pick(list(SCOPE_SURF)), pick([2025, 2025, 2024]), rng.randint(3, 12)
    t = pick(templates_b)
    exp = [dict(name="bridge", sql=(f"select plan_db2_eur, actual_db2_eur, actual_db2_eur - plan_db2_eur as abweichung_eur "
                                   f"from controlling.mart_db2_bridge where fiscal_year = {year} and to_month = {m} "
                                   f"and scope = '{scope}'"))]
    e_surf = ""
    if "{e}" in t:
        e = pick(["mengeneffekt", "preiseffekt", "waehrungseffekt", "mixeffekt"])
        e_surf = {"mengeneffekt": "der Mengeneffekt im DB II", "preiseffekt": "der Preiseffekt im DB II",
                  "waehrungseffekt": "der Währungseffekt", "mixeffekt": "der Mixeffekt im DB II"}[e]
        if e == "waehrungseffekt":
            scope = pick(["3000", "GRUPPE"])
        exp = [dict(name="effect", sql=(f"select {BRIDGE_EFFECT_COL[e]} as effekt_eur from controlling.mart_db2_bridge "
                                        f"where fiscal_year = {year} and to_month = {m} and scope = '{scope}'"))]
    add("bridge", t.format(s=pick(SCOPE_SURF[scope]), mon=MONTHS[m - 1], y=year, e=e_surf), "bridge", expected=exp)

# 4) Product groups (25)
for n in range(25):
    scope, year, m = pick(list(SCOPE_SURF)), pick([2025, 2025, 2024]), rng.randint(2, 12)
    s = pick(SCOPE_SURF[scope])
    if n % 5 == 4:  # ranking of one effect over all product groups
        e = pick(list(PG_EFFECT_COL))
        q = f"{pick(EFFECT_SURF[e])[4:]} je Produktgruppe {s} bis {MONTHS[m - 1]} {year}"
        exp = [dict(name=f"pg{g}", sql=(f"select sum({PG_EFFECT_COL[e]}) as effekt_eur from controlling.mart_pvm_cells "
                                         f"where fiscal_year = {year} and to_month = {m} and material_group = '{g}'"
                                         f"{scope_sql(scope)}")) for g in PG]
    else:
        g = pick(list(PG))
        gs = pick(PG[g])
        e = pick(list(PG_EFFECT_COL))
        t = pick(["Wie hoch ist {e} bei {g} {s} bis {mon} {y}?", "Wie entwickelt sich die Produktgruppe {g} {s} bis {mon} {y}?",
                  "DB I der Produktgruppe {g} {s}, Januar bis {mon} {y}"])
        q = t.format(e=pick(EFFECT_SURF[e]), g=gs, s=s, mon=MONTHS[m - 1], y=year)
        exp = [dict(name="pg", sql=(
            f"select sum(revenue_ist) as umsatz_ist_eur, sum(revenue_plan) as umsatz_plan_eur, sum(db1_ist) as db1_ist_eur, "
            f"sum(db1_plan) as db1_plan_eur, sum({PG_EFFECT_COL[e]}) as effekt_eur from controlling.mart_pvm_cells "
            f"where fiscal_year = {year} and to_month = {m} and material_group = '{g}'{scope_sql(scope)}"))]
    add("product_group", q, "product_group", expected=exp)

# 5) Top cost centres (15)
for _ in range(15):
    scope, year, m = pick(list(SCOPE_SURF)), pick([2025, 2025, 2024]), rng.randint(3, 12)
    top = pick([3, 5])
    t = pick(["Welche Kostenstellen haben {s} bis {mon} {y} die größte Abweichung?",
              "Top {n} Kostenstellen nach Budgetüberschreitung {s}, Januar bis {mon} {y}",
              "Welche {n} Kostenstellen überschreiten {s} ihr Budget bis {mon} {y} am stärksten?"])
    if "{n}" not in t:
        top = 5
    q = t.format(s=pick(SCOPE_SURF[scope]), mon=MONTHS[m - 1], y=year, n=top)
    exp = [dict(name=f"rank{r}", sql=(
        f"select abweichung_eur from (select cost_centre, sum(variance_cc_eur) as abweichung_eur, "
        f"row_number() over (order by sum(variance_cc_eur), cost_centre) as rn from controlling.mart_cost_variance "
        f"where fiscal_year = {year} and to_month = {m}{scope_sql(scope)} group by cost_centre) where rn = {r}"))
        for r in range(1, top + 1)]
    add("cost_centres_top", q, "cost_centres_top", expected=exp)

# 6) One cost centre (15)
for n in range(15):
    year, m = pick([2025, 2025, 2024]), rng.randint(2, 12)
    if n % 3 == 2:
        cc = pick(list(CC_NAMED))
        q = f"Wie sieht die Kostenstelle {CC_NAMED[cc]} bis {MONTHS[m - 1]} {year} aus?"
    else:
        cc = pick(CC_ALL)
        q = pick(["Abweichung der Kostenstelle {c} bis {mon} {y}", "Wie steht die Kostenstelle {c} im Budget, Januar bis {mon} {y}?",
                  "Kostenstelle {c}: Plan und Ist kumuliert bis {mon} {y}"]).format(c=cc, mon=MONTHS[m - 1], y=year)
    exp = [dict(name="cc", sql=(f"select sum(plan_cc_eur) as plan_eur, sum(actual_cc_eur) as ist_eur, "
                                f"sum(variance_cc_eur) as abweichung_eur from controlling.mart_cost_variance "
                                f"where fiscal_year = {year} and to_month = {m} and cost_centre = '{cc}'"))]
    add("cost_centre", q, "cost_centre", expected=exp)

# 7) Order intake (15)
for _ in range(15):
    scope, year, m = pick(list(SCOPE_SURF)), pick([2025, 2025, 2024]), rng.randint(1, 12)
    s = pick(SCOPE_SURF[scope])
    g = pick([None, None, "PG10", "PG20", "PG40"])
    gs = f" {PG[g][0]}" if g else ""
    q = pick(["Wie hoch war der Auftragseingang{g} {s} im {mon} {y}?", "Auftragseingang{g} {s} {mon} {y}",
              "Wie viele Aufträge{g} gingen {s} im {mon} {y} ein (Wert)?"]).format(g=gs, s=s, mon=MONTHS[m - 1], y=year)
    gf = f" and material_group = '{g}'" if g else ""
    exp = [dict(name="oi", sql=(f"select sum(net_value_eur) as auftragseingang_eur from core.fct_order_intake "
                                f"where period = '{year}-{m:02d}'{scope_sql(scope)}{gf}")),
           dict(name="rev", sql=(f"select sum(revenue_eur) as umsatz_eur from core.fct_sales_item "
                                 f"where period = '{year}-{m:02d}'{scope_sql(scope)}{gf}"))]
    add("order_intake", q, "order_intake", expected=exp)

# 8) Forecast (10)
for _ in range(10):
    scope = pick(list(SCOPE_SURF))
    v = pick(["3+9", "6+6", "9+3"])
    vid = {"3+9": "FC3_9", "6+6": "FC6_6", "9+3": "FC9_3"}[v]
    q = pick(["Erreichen wir das Jahresziel 2025 laut Forecast {v} {s}?", "Wie lautet die Hochrechnung {v} für den DB II 2025 {s}?",
              "Prognose DB II 2025 {s}, Version {v}"]).format(v=v, s=pick(SCOPE_SURF[scope]))
    exp = [dict(name="fc", sql=(f"select forecast_db2_eur as prognose_eur, plan_db2_eur as plan_eur from forecast.rolling_forecast "
                                f"where version = '{vid}' and method = 'ml' and scope = '{scope}'"))]
    add("forecast", q, "forecast", expected=exp)

# 9) Row-level security (10): cost-centre owners
owners = {"leitung_instandhaltung": ["1410"], "leitung_fertigung_pumpen": ["1500", "1520"],
          "geschaeftsfuehrung_at": ["2100", "2400", "2500", "2600", "2700", "2800"], "leitung_it": ["1130"]}
for n, (user, own) in enumerate(list(owners.items()) * 3):
    if len([i for i in items if i["category"] == "row_level_security"]) >= 10:
        break
    year, m = 2025, rng.randint(3, 12)
    kind = n // 4
    others = [c for c in CC_ALL if c not in own]
    if kind == 0:
        q = f"Welche Kostenstellen haben bis {MONTHS[m - 1]} {year} die größte Abweichung?"
        cc_in = ", ".join(f"'{c}'" for c in own)
        exp = [dict(name=f"rank{r}", sql=(
            f"select abweichung_eur from (select cost_centre, sum(variance_cc_eur) as abweichung_eur, "
            f"row_number() over (order by sum(variance_cc_eur), cost_centre) as rn from controlling.mart_cost_variance "
            f"where fiscal_year = {year} and to_month = {m} and cost_centre in ({cc_in}) group by cost_centre) "
            f"where rn = {r}")) for r in range(1, min(5, len(own)) + 1)]
        add("row_level_security", q, "cost_centres_top", user=user, expected=exp, forbidden=others)
    elif kind == 1:
        c = pick(others)
        add("row_level_security", f"Abweichung der Kostenstelle {c} bis {MONTHS[m - 1]} {year}", "cost_centre",
            status="no_data", user=user, forbidden=[])
    else:
        add("row_level_security", f"Wie hoch war der DB II im {MONTHS[m - 1]} {year}?", "kpi", status="denied", user=user)

# 10) Out of scope (10)
for q in ["Wie wird das Wetter morgen in Dortmund?", "Schreib mir ein Gedicht über Pumpen.",
          "Wer gewinnt die Bundesliga?", "Was kostet ein Flug nach Wien?", "Wie hoch ist der Aktienkurs von Siemens?",
          "Erzähl mir einen Witz.", "Welche Programmiersprache ist die beste?", "Wie koche ich Spaghetti Carbonara?",
          "Übersetze 'Deckel' ins Englische.", "Was ist die Hauptstadt von Frankreich?"]:
    add("out_of_scope", q, "out_of_scope", status="out_of_scope")

assert len(items) == 200, len(items)
OUT.write_text("# Frozen golden set (ADR-0001, Q3 criterion 2). Generated by eval/build_golden_set.py,\n"
               "# seed 20251231. Expected figures are SQL on controlling/core marts, evaluated at run time.\n"
               + yaml.safe_dump(dict(version=1, items=items), allow_unicode=True, sort_keys=False, width=140),
               encoding="utf-8")
print(f"wrote {len(items)} items to {OUT}")
