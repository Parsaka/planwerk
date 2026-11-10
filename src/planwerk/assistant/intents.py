"""Question understanding: German controlling questions -> intent with typed slots.

The offline router is rule based and deterministic (used in CI and without credentials). The
LLM router (``llm.AzureOpenAIProvider.route``) returns the same structure via function calling;
its output is validated by :func:`Intent.validated` before any query is built, so a model can
never inject free text into SQL.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, replace

INTENTS = ("kpi", "bridge", "product_group", "cost_centres_top", "cost_centre", "order_intake", "forecast",
           "commentary", "method", "out_of_scope")
SCOPES = ("GRUPPE", "1000", "2000", "3000")
SCOPE_TEXT = {"GRUPPE": "Nordwerk-Gruppe", "1000": "Nordwerk GmbH (DE)", "2000": "Nordwerk Austria GmbH (AT)",
              "3000": "Nordwerk Polska Sp. z o.o. (PL)"}
KPIS = ("umsatz", "nettoumsatz", "variable_kosten", "db1", "fixkosten_db2", "db2", "fixkosten_db3", "db3",
        "unternehmensfixkosten", "betriebsergebnis")
KPI_TEXT = {"umsatz": "Umsatz", "nettoumsatz": "Nettoumsatz", "variable_kosten": "variable Kosten",
            "db1": "DB I", "fixkosten_db2": "Fixkosten der Produktgruppen (DB II)", "db2": "DB II",
            "fixkosten_db3": "Bereichsfixkosten (DB III)", "db3": "DB III",
            "unternehmensfixkosten": "Unternehmensfixkosten", "betriebsergebnis": "Betriebsergebnis"}
COST_KPIS = {"variable_kosten", "fixkosten_db2", "fixkosten_db3", "unternehmensfixkosten"}
PRODUCT_GROUPS = {"PG10": "Kreiselpumpen", "PG20": "Dosierpumpen", "PG30": "Ventile und Armaturen",
                  "PG40": "Ersatzteile", "PG50": "Service"}
EFFECTS = ("mengeneffekt", "mixeffekt", "preiseffekt", "materialkosteneffekt", "erloesschmaelerung",
           "fixkosteneffekt", "waehrungseffekt")
EFFECT_TEXT = {"mengeneffekt": "Mengeneffekt", "mixeffekt": "Mixeffekt", "preiseffekt": "Preiseffekt",
               "materialkosteneffekt": "Materialkosteneffekt", "erloesschmaelerung": "Erlösschmälerungen",
               "fixkosteneffekt": "Fixkosteneffekt", "waehrungseffekt": "Währungseffekt"}
MONTHS = {"januar": 1, "jaenner": 1, "jänner": 1, "jan": 1, "februar": 2, "feber": 2, "feb": 2, "maerz": 3,
          "märz": 3, "mrz": 3, "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
          "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10,
          "november": 11, "nov": 11, "dezember": 12, "dez": 12}
MONTH_TEXT = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
              9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}
YEARS = (2023, 2024, 2025)
FORECAST_VERSIONS = ("FC3_9", "FC6_6", "FC9_3")


@dataclass(frozen=True)
class Intent:
    name: str
    scope: str = "GRUPPE"
    year: int = 2025
    month: int = 12
    ytd: bool = False
    kpi: str = "db2"
    product_group: str | None = None
    cost_centre: str | None = None
    effect: str | None = None
    forecast_version: str = "FC9_3"
    top_n: int = 5
    month_given: bool = False

    def validated(self, cost_centres: set[str] | None = None) -> Intent:
        """Reject anything outside the closed vocabularies (also for LLM-produced intents)."""
        if self.name not in INTENTS:
            raise ValueError(f"unknown intent {self.name}")
        if self.scope not in SCOPES:
            raise ValueError(f"unknown scope {self.scope}")
        if self.year not in YEARS or not 1 <= int(self.month) <= 12:
            raise ValueError("period outside the data window")
        if self.kpi not in KPIS:
            raise ValueError(f"unknown kpi {self.kpi}")
        if self.product_group is not None and self.product_group not in PRODUCT_GROUPS:
            raise ValueError("unknown product group")
        if self.effect is not None and self.effect not in EFFECTS:
            raise ValueError("unknown effect")
        if self.forecast_version not in FORECAST_VERSIONS:
            raise ValueError("unknown forecast version")
        if self.cost_centre is not None:
            if not re.fullmatch(r"[123]\d{3}", self.cost_centre):
                raise ValueError("cost centre must be four digits")
            if cost_centres is not None and self.cost_centre not in cost_centres:
                raise ValueError("unknown cost centre")
        if not 1 <= int(self.top_n) <= 10:
            raise ValueError("top_n must be 1..10")
        return replace(self, month=int(self.month), year=int(self.year), top_n=int(self.top_n))

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text).lower()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"\s+", " ", t)


_SCOPE_PATTERNS = [
    ("1000", r"\b(deutschland|de|inland\w*|nordwerk gmbh|buchungskreis 1000|bukrs 1000|1000)\b"),
    ("2000", r"\b(oesterreich\w*|at|austria|wien|buchungskreis 2000|bukrs 2000|2000)\b"),
    ("3000", r"\b(polen|polnisch\w*|pl|polska|buchungskreis 3000|bukrs 3000|3000)\b"),
    ("GRUPPE", r"\b(gruppe|konzern|gesamt|insgesamt|alle gesellschaften|nordwerk-gruppe)\b"),
]
_KPI_PATTERNS = [
    ("db3", r"\b(db ?iii|db ?3|deckungsbeitrag ?(iii|3))\b"),
    ("db2", r"\b(db ?ii|db ?2|deckungsbeitrag ?(ii|2))\b|\bdeckungsbeitr\w*\b(?! ?(i|1|iii|3)\b)"),
    ("db1", r"\b(db ?i|db ?1|deckungsbeitrag ?(i|1)|rohertrag)\b"),
    ("betriebsergebnis", r"\b(betriebsergebnis\w*|ebit|operatives ergebnis|ergebnis)\b"),
    ("unternehmensfixkosten", r"\b(unternehmensfixkosten|verwaltungskosten|overhead)\b"),
    ("fixkosten_db3", r"\b(bereichsfixkosten|fixkosten (der )?bereiche)\b"),
    ("fixkosten_db2", r"\b(produktgruppenfixkosten|fixkosten (der )?produktgruppen|fertigungsfixkosten|fixkosten)\b"),
    ("variable_kosten", r"\b(variable kosten|variablen kosten|materialkosten|wareneinsatz|materialeinsatz)\b"),
    ("nettoumsatz", r"\b(nettoumsatz|nettoerloes\w*|netto-umsatz)\b"),
    ("umsatz", r"\b(umsatz|umsaetze|umsatzerloes\w*|erloes\w*)\b"),
]
_EFFECT_PATTERNS = [
    ("preiseffekt", r"\b(preiseffekt|preisabweichung|preise?\b|preiserhoehung\w*)"),
    ("mengeneffekt", r"\b(mengeneffekt|mengenabweichung|absatzmenge\w*|volumen\w*)\b"),
    ("mixeffekt", r"\b(mixeffekt|mix|sortiment\w*)\b"),
    ("materialkosteneffekt", r"\b(materialkosteneffekt|materialpreis\w*|einstandspreis\w*)\b"),
    ("erloesschmaelerung", r"\b(erloesschmaelerung\w*|skont\w*)\b"),
    ("waehrungseffekt", r"\b(waehrung\w*|wechselkurs\w*|fx|zloty)\b"),
    ("fixkosteneffekt", r"\b(fixkosteneffekt)\b"),
]
_PG_PATTERNS = [
    ("PG10", r"\b(pg ?10|kreiselpumpe\w*)\b"), ("PG20", r"\b(pg ?20|dosierpumpe\w*)\b"),
    ("PG30", r"\b(pg ?30|ventil\w*|armatur\w*)\b"), ("PG40", r"\b(pg ?40|ersatzteil\w*)\b"),
    ("PG50", r"\b(pg ?50|service ?(geschaeft|umsatz|leistungen)|dienstleistung\w*)\b"),
]


def _find(patterns, t):
    for key, pat in patterns:
        if re.search(pat, t):
            return key
    return None


_METHOD = re.compile(
    r"^(was (ist|sind|bedeutet|bedeuten|versteht man|heisst|gehoert|enthaelt|steht|regelt|tun)"
    r"|wie (wird|werden|berechnet|ermittelt|funktioniert|definiert|laeuft|lange|oft)"
    r"|wer (darf|sieht|pflegt|genehmigt|ist verantwortlich|hat zugriff)"
    r"|nach welche\w* (verfahren|methode|regel|logik|schluessel)|mit welche\w* (schluessel|verfahren|methode)"
    r"|welche (regel|methode|treiber|felder|rolle|daten|abnahme|nichtfunktional|personenbezogen|kennzahl|kriteri|schritt|verfahren)\w*"
    r"|woraus|(ab )?wann (gilt|wird|wuerde)|ist (fuer|eine|ein)\b|in welche\w* risikoklasse"
    r"|erklaer\w* (mir )?(den|die|das) (begriff|methode|logik|unterschied|berechnung))")


def parse(question: str, as_of: tuple[int, int] = (2025, 12), cost_centres: dict[str, str] | None = None) -> Intent:
    """Rule-based German intent parser. ``cost_centres`` maps number -> name for name lookup."""
    t = _norm(question)
    year, outside = None, False
    for m in re.finditer(r"\b(20\d\d)\b", t):
        if int(m.group(1)) in YEARS:
            year = int(m.group(1))
        elif m.group(1) != "2000" and not re.search(rf"(kostenstelle|kst\.?) ?{m.group(1)}", t):
            outside = True  # a year outside the data window: never silently answer another year
    month = None
    m = re.search(r"\b(20\d\d)-(\d{1,2})\b", t) or re.search(r"\b(\d{1,2})[/.](20\d\d)\b", t)
    if m:
        a, b = m.groups()
        year, month = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
    if month is None:  # the last month named wins ("Januar bis Juni" -> Juni)
        best = -1
        for name, num in MONTHS.items():
            for mm in re.finditer(rf"\b{_norm(name)}\b", t):
                if mm.start() > best:
                    best, month = mm.start(), num
    q = re.search(r"\b(q[1-4]|[1-4]\. quartal)\b", t)
    ytd = bool(re.search(r"\b(kumuliert\w*|ytd|year to date|seit jahresbeginn|bis (ende )?\w+|bis einschliesslich"
                         r"|jahr|gesamtjahr|im jahr|laufenden jahr\w*|aufgelaufen\w*)\b", t))
    if q and month is None:
        month, ytd = int(re.search(r"[1-4]", q.group(1)).group(0)) * 3, True
    month_given = month is not None
    if year is None:
        year = as_of[0]
    if month is None:
        month = as_of[1] if year == as_of[0] else 12
        ytd = True
    scope = _find(_SCOPE_PATTERNS, t) or "GRUPPE"
    kpi = _find(_KPI_PATTERNS, t)
    pg = _find(_PG_PATTERNS, t)
    effect = _find(_EFFECT_PATTERNS, t)
    cc = None
    for m in re.finditer(r"\b([123]\d{3})\b", t):
        num = m.group(1)
        if num in ("1000", "2000", "3000") or (2020 <= int(num) <= 2030):
            continue
        cc = num
    m = re.search(r"\b(kostenstelle|kst\.?) ?(\d{3,6})\b", t)
    if m and not (2020 <= int(m.group(2)) <= 2030):
        cc = m.group(2)  # validated later: an unknown number is rejected, never mapped to another one
    if cc is None and cost_centres and re.search(r"\bkostenstelle\b", t):
        for num, name in sorted(cost_centres.items(), key=lambda kv: -len(kv[1])):
            if _norm(name) in t:
                cc = num
                break
    version = "FC9_3"
    mv = re.search(r"\b(3 ?\+ ?9|6 ?\+ ?6|9 ?\+ ?3)\b", t)
    if mv:
        version = {"3": "FC3_9", "6": "FC6_6", "9": "FC9_3"}[mv.group(1)[0]]
    top = re.search(r"\btop ?(\d{1,2})\b|\b(\d{1,2}) (groessten|wichtigsten|hoechsten)\b", t)
    top_n = int(next(g for g in top.groups() if g)) if top else 5

    if outside or (re.search(r"\b(ignoriere|ignore|vergiss|system ?prompt|anweisung\w*|jailbreak)\b", t)
                   and not kpi):
        name = "out_of_scope"
    elif not month_given and not re.search(r"\b20\d\d\b", t) and _METHOD.search(t):
        name = "method"  # how something is defined or regulated: answered from the documents, not the data
    elif re.search(r"\b(\w*kommentar\w*|monatsbericht\w*|management summary)\b", t) or (
            re.search(r"\b(schreib\w*|formulier\w*|erstell\w*|verfass\w*)\b", t)
            and re.search(r"\b(monat\w*|bericht\w*|zusammenfassung)\b", t)):
        name = "commentary"
    elif re.search(r"\b(prognose\w*|forecast\w*|hochrechnung\w*|jahresziel\w*|zielerreichung|erwartet\w*"
                   r"|landen|voraussicht\w*|erreichen)\b", t):
        name = "forecast"
    elif re.search(r"\bauftragseing\w*|\bauftraege\b|\bbestellungen\b|\bauftragsbestand\b|book.to.bill", t):
        name = "order_intake"
    elif cc is not None:
        name = "cost_centre"
    elif re.search(r"\bkostenstellen\b|\bwelche kostenstelle\b|\bkostenstelle mit\b", t):
        name = "cost_centres_top"
    elif pg is not None or (re.search(r"\bproduktgruppe\w*\b", t) and kpi != "fixkosten_db2"):
        name = "product_group"
    elif effect is not None or re.search(r"\b(warum|wieso|weshalb|ursache\w*|treib\w*|\w*bruecke|erklaer\w*"
                                         r"|abweichungsanalyse|zusammensetz\w*|woran)\b", t):
        name = "bridge"
    elif kpi is not None or re.search(r"\b(plan\w*|budget\w*|abweichung\w*|ist-?(wert\w*|zahl\w*|kosten)|soll-ist)\b", t):
        name = "kpi"
    else:
        name = "out_of_scope"
    if name in ("bridge", "product_group", "cost_centres_top", "cost_centre", "forecast"):
        ytd = True  # these views are year to date by construction
    return Intent(name=name, scope=scope, year=year, month=month, ytd=ytd, kpi=kpi or "db2", product_group=pg,
                  cost_centre=cc, effect=effect, forecast_version=version, top_n=top_n,
                  month_given=month_given)


def period_text(i: Intent) -> str:
    if i.ytd:
        return f"Januar bis {MONTH_TEXT[i.month]} {i.year}" if i.month < 12 else f"Gesamtjahr {i.year}"
    return f"{MONTH_TEXT[i.month]} {i.year}"


def mentioned(question: str) -> dict:
    """Years and cost-centre numbers literally present in the question (for consistency checks)."""
    t = _norm(question)
    ccs = {m.group(2) for m in re.finditer(r"\b(kostenstelle|kst\.?) ?(\d{3,6})\b", t)}
    years = {int(y) for y in re.findall(r"\b(20\d\d)\b", t) if y != "2000" and y not in ccs}
    return dict(years=years, cost_centres=ccs)


def consistent(question: str, i: Intent) -> bool:
    """Deterministic cross-check of a (possibly model-produced) intent against the question: never
    answer a year or a cost centre other than the one the user named."""
    m = mentioned(question)
    if m["years"] and (i.year not in m["years"] or not m["years"] <= set(YEARS)):
        return False
    if m["cost_centres"] and i.name == "cost_centre" and i.cost_centre not in m["cost_centres"]:
        return False
    return True
