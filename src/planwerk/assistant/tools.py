"""Read-only data tools: one parameterised SQL per intent, run through the SQL guard, turned
into a fact sheet. These are the only functions that touch the warehouse.

All literals come from a validated :class:`Intent` (closed vocabularies, integers), and every
statement still passes :func:`sql_guard.validate` before execution (defence in depth).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache

import duckdb

from planwerk.assistant.facts import FactSheet
from planwerk.assistant.intents import (
    COST_KPIS,
    EFFECT_TEXT,
    KPI_TEXT,
    MONTH_TEXT,
    PRODUCT_GROUPS,
    SCOPE_TEXT,
    Intent,
    period_text,
)
from planwerk.assistant.sql_guard import validate
from planwerk.forecast.evaluation import MISS_THRESHOLD
from planwerk.generator.config import REPO_ROOT

ACCESS_FILE = REPO_ROOT / "dbt" / "seeds" / "cost_centre_access.csv"
FULL_ACCESS_ROLES = {"CONTROLLER", "MANAGEMENT"}
CC_OWNER_INTENTS = {"cost_centre", "cost_centres_top", "out_of_scope"}


class AccessDenied(PermissionError):
    pass


@lru_cache(maxsize=1)
def access_list() -> dict[str, dict]:
    users: dict[str, dict] = {}
    with open(ACCESS_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            u = users.setdefault(r["user_name"].lower(), dict(role=r["role"], cost_centres=set()))
            u["cost_centres"].add(r["cost_centre"])
    return users


def authorise(user: str, intent: Intent) -> dict:
    """Intent-level authorisation (row-level security is enforced in the views themselves)."""
    if not re.fullmatch(r"[a-z_]{3,40}", user or ""):
        raise AccessDenied("Unbekannter Benutzer")
    u = access_list().get(user)
    if u is None:
        raise AccessDenied("Unbekannter Benutzer")
    if u["role"] not in FULL_ACCESS_ROLES and intent.name not in CC_OWNER_INTENTS:
        raise AccessDenied("Diese Auswertung ist Controlling und Geschäftsführung vorbehalten. "
                           "Als Kostenstellenverantwortliche/r sehen Sie Ihre Kostenstellen.")
    return u


@dataclass
class ToolResult:
    sheet: FactSheet
    sql: list[str] = field(default_factory=list)
    rows: dict[str, list[dict]] = field(default_factory=dict)
    empty: bool = False
    context: dict = field(default_factory=dict)


def _run(con: duckdb.DuckDBPyConnection, sql: str, res: ToolResult, key: str) -> list[dict]:
    safe = validate(sql)
    res.sql.append(safe)
    cur = con.execute(safe)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
    res.rows[key] = rows
    return rows


def set_user(con: duckdb.DuckDBPyConnection, user: str) -> None:
    if not re.fullmatch(r"[a-z_]{3,40}", user):
        raise AccessDenied("Unbekannter Benutzer")
    con.execute(f"set variable planwerk_user = '{user}'")


def _scope_filter(i: Intent, col: str = "bereich") -> str:
    return "" if i.scope == "GRUPPE" else f" and {col} = '{i.scope}'"


def _ctx(i: Intent) -> dict:
    return dict(scope_text=SCOPE_TEXT[i.scope], period_text=period_text(i), kpi_text=KPI_TEXT[i.kpi],
                month_text=MONTH_TEXT[i.month], year=i.year)


# --- KPI ---------------------------------------------------------------------------------------

def kpi(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    mfilter = f"monat <= {i.month}" if i.ytd else f"monat = {i.month}"
    sql = f"""select jahr, sum(ist_eur) as ist_eur, sum(plan_eur) as plan_eur
              from sem_kennzahlen_monat
              where bereich = '{i.scope}' and kennzahl = '{i.kpi}' and jahr in ({i.year}, {i.year - 1})
                and {mfilter}
              group by jahr order by jahr"""
    rows = {r["jahr"]: r for r in _run(con, sql, res, "kpi")}
    cur = rows.get(i.year)
    if cur is None:
        res.empty = True
        return res
    s = res.sheet
    ist, plan = float(cur["ist_eur"]), float(cur["plan_eur"])
    src = "semantic.sem_kennzahlen_monat"
    s.add("ist", f"{KPI_TEXT[i.kpi]} Ist", ist, "EUR", src)
    s.add("plan", f"{KPI_TEXT[i.kpi]} Plan", plan, "EUR", src)
    s.add("abw", "Abweichung Ist - Plan", ist - plan, "EUR", src)
    if plan:
        s.add("abw_pct", "Abweichung in % vom Plan", (ist - plan) / abs(plan), "PCT", src)
    prev = rows.get(i.year - 1)
    if prev is not None and float(prev["ist_eur"]):
        s.add("vj", f"{KPI_TEXT[i.kpi]} Vorjahr (Ist)", float(prev["ist_eur"]), "EUR", src)
        s.add("vj_pct", "Veränderung zum Vorjahr", ist / float(prev["ist_eur"]) - 1, "PCT", src)
    res.context["is_cost"] = i.kpi in COST_KPIS
    return res


# --- Budget bridge -----------------------------------------------------------------------------

BRIDGE_COLS = [("mengeneffekt", "mengeneffekt_eur"), ("mixeffekt", "mixeffekt_eur"),
               ("preiseffekt", "preiseffekt_eur"), ("materialkosteneffekt", "materialkosteneffekt_eur"),
               ("erloesschmaelerung", "erloesschmaelerung_eur"), ("fixkosteneffekt", "fixkosteneffekt_db2_eur"),
               ("waehrungseffekt", "waehrungseffekt_eur")]


def bridge(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    cols = ", ".join(c for _, c in BRIDGE_COLS)
    sql = f"""select plan_db2_eur, {cols}, ist_db2_eur
              from sem_abweichungsbruecke
              where jahr = {i.year} and bis_monat = {i.month} and bereich = '{i.scope}'"""
    rows = _run(con, sql, res, "bridge")
    if not rows:
        res.empty = True
        return res
    r, s, src = rows[0], res.sheet, "semantic.sem_abweichungsbruecke"
    plan, ist = float(r["plan_db2_eur"]), float(r["ist_db2_eur"])
    s.add("plan", "DB II Plan", plan, "EUR", src)
    s.add("ist", "DB II Ist", ist, "EUR", src)
    s.add("abw", "Abweichung DB II Ist - Plan", ist - plan, "EUR", src)
    if plan:
        s.add("abw_pct", "Abweichung DB II in % vom Plan", (ist - plan) / abs(plan), "PCT", src)
    for k, c in BRIDGE_COLS:
        s.add(k, EFFECT_TEXT[k] + " (positiv = günstig)", float(r[c] or 0.0), "EUR", src)
    effects = sorted(((k, s.facts[k].value) for k, _ in BRIDGE_COLS), key=lambda kv: kv[1])
    res.context["ranked_effects"] = [k for k, _ in effects]
    res.context["focus_effect"] = i.effect
    return res


# --- Product groups ----------------------------------------------------------------------------

PG_COLS = ["ist_umsatz_eur", "plan_umsatz_eur", "ist_db1_eur", "plan_db1_eur", "preiseffekt_eur",
           "mengeneffekt_eur", "mixeffekt_eur", "materialkosteneffekt_eur"]
PG_LABEL = {"ist_umsatz_eur": "Umsatz Ist", "plan_umsatz_eur": "Umsatz Plan", "ist_db1_eur": "DB I Ist",
            "plan_db1_eur": "DB I Plan", "preiseffekt_eur": "Preiseffekt", "mengeneffekt_eur": "Mengeneffekt",
            "mixeffekt_eur": "Mixeffekt", "materialkosteneffekt_eur": "Materialkosteneffekt"}


def product_group(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    sums = ", ".join(f"sum({c}) as {c}" for c in PG_COLS)
    sql = f"""select produktgruppe, {sums}
              from sem_produktgruppen
              where jahr = {i.year} and bis_monat = {i.month}{_scope_filter(i)}
              group by produktgruppe order by produktgruppe"""
    rows = _run(con, sql, res, "pg")
    if not rows:
        res.empty = True
        return res
    s, src = res.sheet, "semantic.sem_produktgruppen"
    sel = [r for r in rows if i.product_group in (None, r["produktgruppe"])]
    for r in sel:
        pg = r["produktgruppe"].lower()
        for c in PG_COLS:
            s.add(f"{pg}_{c.replace('_eur', '')}", f"{PRODUCT_GROUPS[r['produktgruppe']]}: {PG_LABEL[c]}",
                  float(r[c] or 0.0), "EUR", src)
        s.add(f"{pg}_abw_db1", f"{PRODUCT_GROUPS[r['produktgruppe']]}: Abweichung DB I",
              float(r["ist_db1_eur"]) - float(r["plan_db1_eur"]), "EUR", src)
    eff = (i.effect or "preiseffekt") + "_eur"
    if eff not in PG_COLS:
        eff = "preiseffekt_eur"
    res.context.update(product_groups=[r["produktgruppe"] for r in sel], focus_col=eff.replace("_eur", ""),
                       ranked=[r["produktgruppe"] for r in sorted(sel, key=lambda r: float(r[eff] or 0))])
    return res


# --- Cost centres ------------------------------------------------------------------------------

def cost_centres_top(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    sql = f"""select kostenstelle, kostenstelle_text, verantwortlich, plan_eur, ist_eur, abweichung_eur
              from sem_kostenstellen
              where jahr = {i.year} and bis_monat = {i.month}{_scope_filter(i)}
              order by abweichung_eur asc, kostenstelle limit {i.top_n}"""
    rows = _run(con, sql, res, "cc")
    if not rows:
        res.empty = True
        return res
    s, src = res.sheet, "semantic.sem_kostenstellen"
    for r in rows:
        k = r["kostenstelle"]
        s.allowed_tokens.add(k)
        s.add(f"kst{k}_plan", f"KSt {k} {r['kostenstelle_text']}: Plan", float(r["plan_eur"]), "EUR", src)
        s.add(f"kst{k}_ist", f"KSt {k} {r['kostenstelle_text']}: Ist", float(r["ist_eur"]), "EUR", src)
        s.add(f"kst{k}_abw", f"KSt {k} {r['kostenstelle_text']}: Abweichung Plan - Ist (positiv = günstig)",
              float(r["abweichung_eur"]), "EUR", src)
    res.context["cost_centres"] = [(r["kostenstelle"], r["kostenstelle_text"], r["verantwortlich"]) for r in rows]
    s.allowed_tokens.add(str(len(rows)))
    return res


def cost_centre(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    sql = f"""select kostenstelle_text, konto, konto_text, plan_eur, ist_eur, abweichung_eur
              from sem_kostenarten
              where jahr = {i.year} and bis_monat = {i.month} and kostenstelle = '{i.cost_centre}'
              order by abweichung_eur asc, konto"""
    rows = _run(con, sql, res, "cc_detail")
    if not rows:
        res.empty = True  # no data or no permission: the answer does not distinguish (no existence leak)
        return res
    s, src = res.sheet, "semantic.sem_kostenarten"
    s.allowed_tokens.add(i.cost_centre)
    plan = sum(float(r["plan_eur"]) for r in rows)
    ist = sum(float(r["ist_eur"]) for r in rows)
    s.add("plan", "Primärkosten Plan", plan, "EUR", src)
    s.add("ist", "Primärkosten Ist", ist, "EUR", src)
    s.add("abw", "Abweichung Plan - Ist (positiv = günstig)", plan - ist, "EUR", src)
    if plan:
        s.add("abw_pct", "Abweichung in % vom Plan (positiv = günstig)", (plan - ist) / abs(plan), "PCT", src)
    top = [r for r in rows if abs(float(r["abweichung_eur"])) >= 1000.0][:3]  # material positions only
    for r in top:
        s.allowed_tokens.add(r["konto"])
        s.add(f"konto{r['konto']}_abw", f"Konto {r['konto']} {r['konto_text']}: Abweichung",
              float(r["abweichung_eur"]), "EUR", src)
    res.context.update(cc=i.cost_centre, cc_text=rows[0]["kostenstelle_text"],
                       accounts=[(r["konto"], r["konto_text"]) for r in top])
    return res


# --- Order intake ------------------------------------------------------------------------------

def order_intake(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    mfilter = f"monat <= {i.month}" if i.ytd else f"monat = {i.month}"
    pg = f" and produktgruppe = '{i.product_group}'" if i.product_group else ""
    sql = f"""select jahr, sum(auftragseingang_eur) as ae, sum(umsatz_eur) as umsatz
              from sem_auftragseingang
              where jahr in ({i.year}, {i.year - 1}) and {mfilter}{_scope_filter(i)}{pg}
              group by jahr order by jahr"""
    rows = {r["jahr"]: r for r in _run(con, sql, res, "oi")}
    cur = rows.get(i.year)
    if cur is None or not cur["ae"]:
        res.empty = True
        return res
    s, src = res.sheet, "semantic.sem_auftragseingang"
    s.add("ae", "Auftragseingang", float(cur["ae"]), "EUR", src)
    s.add("umsatz", "Umsatz (fakturiert)", float(cur["umsatz"] or 0.0), "EUR", src)
    if cur["umsatz"]:
        s.add("btb", "Book-to-Bill (Auftragseingang / Umsatz)", float(cur["ae"]) / float(cur["umsatz"]), "DEC", src)
    prev = rows.get(i.year - 1)
    if prev is not None and prev["ae"]:
        s.add("ae_vj", "Auftragseingang Vorjahr", float(prev["ae"]), "EUR", src)
        s.add("ae_vj_pct", "Veränderung zum Vorjahr", float(cur["ae"]) / float(prev["ae"]) - 1, "PCT", src)
    res.context["pg_text"] = PRODUCT_GROUPS.get(i.product_group or "", "")
    return res


# --- Forecast ----------------------------------------------------------------------------------

def forecast(con, i: Intent) -> ToolResult:
    res = ToolResult(FactSheet(), context=_ctx(i))
    sql = f"""select methode, prognose_db2_eur, plan_db2_eur, ziel_verfehlt, bekannte_monate
              from sem_prognose
              where jahr = {i.year} and version = '{i.forecast_version}' and bereich = '{i.scope}'
              order by methode"""
    rows = {r["methode"]: r for r in _run(con, sql, res, "fc")}
    if "ml" not in rows:
        res.empty = True
        return res
    s, src = res.sheet, "semantic.sem_prognose"
    plan = float(rows["ml"]["plan_db2_eur"])
    s.add("plan", f"DB II Plan {i.year}", plan, "EUR", src)
    for meth, label in (("ml", "ML-Prognose"), ("straight_line", "lineare Hochrechnung"),
                        ("seasonal_naive", "saisonale Hochrechnung")):
        if meth in rows:
            fc = float(rows[meth]["prognose_db2_eur"])
            s.add(f"fc_{meth}", f"DB II {label}", fc, "EUR", src)
            s.add(f"fc_{meth}_pct", f"{label}: Abweichung zum Plan", fc / plan - 1 if plan else 0.0, "PCT", src)
    s.add("schwelle", "Warnschwelle (Anteil am Plan)", MISS_THRESHOLD, "PCT", "ADR-0001")
    s.add("luecke", "Lücke ML-Prognose zum Plan", float(rows["ml"]["prognose_db2_eur"]) - plan, "EUR", src)
    k = int(rows["ml"]["bekannte_monate"])
    s.allowed_tokens.update({str(k), str(12 - k), f"{k}+{12 - k}", f"{k} + {12 - k}"})
    res.context.update(miss=bool(rows["ml"]["ziel_verfehlt"]), known=k,
                       straight_miss=bool(rows.get("straight_line", {}).get("ziel_verfehlt", False)))
    return res


TOOLS = {"kpi": kpi, "bridge": bridge, "product_group": product_group, "cost_centres_top": cost_centres_top,
         "cost_centre": cost_centre, "order_intake": order_intake, "forecast": forecast}


def free_sql(con, sql: str) -> ToolResult:
    """LLM-written SQL (validated). Every numeric cell becomes a fact so it can be verified."""
    res = ToolResult(FactSheet())
    rows = _run(con, sql, res, "free")
    for n, r in enumerate(rows[:50]):
        for c, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                unit = "PCT" if c.endswith("_pct") else ("EUR" if c.endswith("_eur") else "INT")
                res.sheet.add(f"r{n}_{re.sub(r'[^a-z0-9_]', '_', c.lower())}", f"Zeile {n + 1}, {c}", float(v), unit,
                              "free_sql")
            elif isinstance(v, str) and re.fullmatch(r"\d{1,7}", v):
                res.sheet.allowed_tokens.add(v)
    res.empty = not rows
    return res


def cost_centre_names(con) -> dict[str, str]:
    rows = con.execute("select distinct kostenstelle, kostenstelle_text from semantic.sem_kostenstellen").fetchall()
    return {k: t for k, t in rows}
