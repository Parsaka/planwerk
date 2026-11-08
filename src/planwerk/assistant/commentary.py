"""Month-end controlling commentary (Q3): fact sheet per scope and month, German draft with
placeholders, optional LLM rewrite, verification of every number.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from planwerk.assistant import tools as T
from planwerk.assistant.facts import FactSheet
from planwerk.assistant.intents import EFFECT_TEXT, MONTH_TEXT, PRODUCT_GROUPS, SCOPE_TEXT, Intent

COMMENTARY_SYSTEM_PROMPT = """Du schreibst den monatlichen Controlling-Kommentar der Nordwerk-Gruppe (simulierte Daten)
für die Geschäftsführung. Regeln, ohne Ausnahme:
1. Keine Ziffern tippen: jede Zahl nur als Platzhalter {{f:ID}} bzw. {{f:ID|signed}} aus dem Faktenblatt.
   Jahreszahlen, Kostenstellen- und Kontonummern aus dem Entwurf dürfen bleiben.
2. Nicht rechnen, keine neuen Zahlen, keine Ursachen erfinden, die nicht im Faktenblatt stehen.
3. Wertungen (günstig/ungünstig, über/unter Plan) aus dem Entwurf übernehmen, nicht umkehren.
4. Gliederung beibehalten (Überschriften mit ###), sachlicher Controlling-Stil, höchstens 220 Wörter.
"""


@dataclass
class CommentaryInput:
    sheet: FactSheet
    draft: str
    sql: list[str]
    scope: str
    year: int
    month: int


def _merge(dst: FactSheet, src: FactSheet, prefix: str) -> None:
    for f in src.facts.values():
        dst.add(f"{prefix}_{f.id}", f.label, f.value, f.unit, f.source)
    dst.allowed_tokens |= src.allowed_tokens


def _version_for(month: int) -> str | None:
    if month >= 12 or month < 3:
        return None
    return "FC3_9" if month < 6 else ("FC6_6" if month < 9 else "FC9_3")


def _art(effect: str) -> str:
    return ("die " if effect == "erloesschmaelerung" else "der ") + EFFECT_TEXT[effect]


def _verb(effects: list[str]) -> str:
    return "wirken" if len(effects) > 1 or effects[0] == "erloesschmaelerung" else "wirkt"


def build(con, scope: str, year: int, month: int) -> CommentaryInput:
    base = Intent(name="kpi", scope=scope, year=year, month=month, kpi="db2", month_given=True)
    sheet, sql = FactSheet(), []
    parts: list[str] = []

    m = T.kpi(con, replace(base, ytd=False))
    y = T.kpi(con, replace(base, ytd=True))
    u = T.kpi(con, replace(base, ytd=True, kpi="umsatz"))
    e = T.kpi(con, replace(base, ytd=True, kpi="betriebsergebnis"))
    for pre, r in (("m", m), ("y", y), ("u", u), ("e", e)):
        _merge(sheet, r.sheet, pre)
        sql += r.sql
    head = f"### {SCOPE_TEXT[scope]} – {MONTH_TEXT[month]} {year}\n\n"
    ytd_txt = f"Januar bis {MONTH_TEXT[month]}" if month > 1 else "Januar"

    def pos(fid: str) -> str:
        v = sheet.facts[fid].value
        return "über" if v > 0.5 else ("unter" if v < -0.5 else "auf")

    parts.append(
        "**Überblick.** Der DB II lag im " + MONTH_TEXT[month] + " bei {{f:m_ist}} und damit {{f:m_abw|signed}} "
        "({{f:m_abw_pct|signed}}) " + pos("m_abw") + " Plan. Kumuliert " + ytd_txt + " erreicht der DB II "
        "{{f:y_ist}} gegenüber {{f:y_plan}} im Plan ({{f:y_abw|signed}}, {{f:y_abw_pct|signed}}). Der Umsatz "
        "liegt kumuliert bei {{f:u_ist}} ({{f:u_abw_pct|signed}} zum Plan), das Betriebsergebnis bei {{f:e_ist}} "
        "(Plan {{f:e_plan}}).")

    b = T.bridge(con, replace(base, ytd=True))
    sql += b.sql
    if not b.empty:
        _merge(sheet, b.sheet, "b")
        neg = [k for k in b.context["ranked_effects"] if b.sheet.facts[k].value < -0.5][:3]
        posit = [k for k in reversed(b.context["ranked_effects"]) if b.sheet.facts[k].value > 0.5][:2]
        txt = "**Abweichungsanalyse DB II (kumuliert, positiv = günstig).** "
        if neg:
            txt += f"Belastend {_verb(neg)} vor allem " + _join([f"{_art(k)} ({{{{f:b_{k}|signed}}}})"
                                                                 for k in neg]) + ". "
        if posit:
            txt += f"Entlastend {_verb(posit)} " + _join([f"{_art(k)} ({{{{f:b_{k}|signed}}}})"
                                                          for k in posit]) + "."
        parts.append(txt.strip())

    p = T.product_group(con, replace(base, name="product_group", ytd=True))
    sql += p.sql
    if not p.empty:
        abw = {g: p.sheet.facts[f"{g.lower()}_abw_db1"].value for g in p.context["product_groups"]}
        worst = min(abw, key=abw.get)
        best = max(abw, key=abw.get)
        sub = FactSheet()
        for g in {worst, best}:
            for k in ("abw_db1", "preiseffekt", "mengeneffekt", "mixeffekt"):
                f = p.sheet.facts[f"{g.lower()}_{k}"]
                sub.add(f.id, f.label, f.value, f.unit, f.source)
        _merge(sheet, sub, "p")
        w = worst.lower()
        txt = (f"**Produktgruppen.** Die größte DB-I-Abweichung zeigt die Produktgruppe {PRODUCT_GROUPS[worst]} "
               f"({worst}) mit "
               f"{{{{f:p_{w}_abw_db1|signed}}}}; darin Preiseffekt {{{{f:p_{w}_preiseffekt|signed}}}}, "
               f"Mengeneffekt {{{{f:p_{w}_mengeneffekt|signed}}}} und Mixeffekt {{{{f:p_{w}_mixeffekt|signed}}}}.")
        if best != worst and abw[best] > 0.5:
            txt += (f" Die beste Entwicklung zeigt die Produktgruppe {PRODUCT_GROUPS[best]} ({best}) mit "
                    f"{{{{f:p_{best.lower()}_abw_db1|signed}}}}.")
        parts.append(txt)

    c = T.cost_centres_top(con, replace(base, name="cost_centres_top", ytd=True, top_n=2))
    sql += c.sql
    if not c.empty:
        _merge(sheet, c.sheet, "c")
        items = [(k, n) for k, n, _ in c.context["cost_centres"] if c.sheet.facts[f"kst{k}_abw"].value < -5000.0]
        if items:
            parts.append("**Kostenstellen.** Die größten ungünstigen Primärkostenabweichungen (Plan − Ist) haben "
                         + _join([f"{k} {n} ({{{{f:c_kst{k}_abw|signed}}}})" for k, n in items]) + ".")
        else:
            parts.append("**Kostenstellen.** Keine Kostenstelle überschreitet kumuliert ihr Primärkostenbudget "
                         "nennenswert (Schwelle {{f:c_schwelle}}).")
            sheet.add("c_schwelle", "Wesentlichkeitsschwelle Kostenstellen", 5000.0, "EUR", "Fachkonzept")

    o = T.order_intake(con, replace(base, name="order_intake", ytd=False))
    sql += o.sql
    if not o.empty and "btb" in o.sheet.facts:
        _merge(sheet, o.sheet, "o")
        btb = o.sheet.facts["btb"].value
        parts.append("**Auftragseingang.** Im " + MONTH_TEXT[month] + " gingen Aufträge über {{f:o_ae}} ein, "
                     "bei einem fakturierten Umsatz von {{f:o_umsatz}} (Book-to-Bill {{f:o_btb}}); "
                     + ("der Auftragsbestand wächst." if btb > 1.0 else "der Auftragsbestand wird abgebaut."))

    v = _version_for(month)
    if v:
        f = T.forecast(con, replace(base, name="forecast", ytd=True, forecast_version=v))
        sql += f.sql
        if not f.empty:
            _merge(sheet, f.sheet, "f")
            k = f.context["known"]
            parts.append(f"**Ausblick.** Der Rolling Forecast {k}+{12 - k} erwartet für {year} einen DB II von "
                         "{{f:f_fc_ml}} ({{f:f_fc_ml_pct|signed}} zum Plan). "
                         + ("Das Jahresziel ist damit gefährdet; Gegenmaßnahmen sollten im nächsten "
                            "Management-Meeting beschlossen werden." if f.context["miss"]
                            else "Das Jahresziel ist nach aktuellem Stand erreichbar."))
    elif month == 12:
        parts.append("**Ausblick.** Mit dem Dezember ist das Geschäftsjahr abgeschlossen; die Werte bilden "
                     "die Basis für den Jahresabschluss und die Planung des Folgejahres.")
    draft = head + "\n\n".join(parts) + "\n\n_Simulierte Daten (Nordwerk GmbH)._"
    return CommentaryInput(sheet, draft, sql, scope, year, month)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " und " + items[-1]


def user_prompt(ci: CommentaryInput) -> str:
    return (f"Faktenblatt ({SCOPE_TEXT[ci.scope]}, {MONTH_TEXT[ci.month]} {ci.year}):\n{ci.sheet.for_prompt()}\n\n"
            f"Entwurf mit Platzhaltern (inhaltlich korrekt; formuliere ihn als flüssigen Kommentar, behalte "
            f"alle Platzhalter, Wertungen und Überschriften):\n{ci.draft}\n\nAntworte nur mit dem Kommentar.")
