"""German Excel month-end report (Monatsbericht) for the simulated Nordwerk group.

    python -m planwerk.reporting.excel_report [--year 2025 --month 12] [--out reports/out]

The workbook is formula-driven: the user picks year, month and company on the cover sheet and every
report sheet recalculates (SUMMEWENNS/INDEX/VERGLEICH on the data sheets). A lookup sheet uses
XVERWEIS (Excel 365), the data sheets are Excel tables ready for PivotTables, and the Power Query
sheet holds the M code to refresh the data from the CSV export written next to the workbook.

Build steps: openpyxl writes formulas -> LibreOffice recalculates (cached values, error check) ->
the XVERWEIS cells are injected into the sheet XML with the verified cached values (LibreOffice
cannot evaluate XLOOKUP, Excel can).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from planwerk.generator.config import REPO_ROOT
from planwerk.warehouse import connect

FONT = "Arial"
NAVY = "1F3864"
F_TITLE = Font(name=FONT, size=16, bold=True, color=NAVY)
F_H = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_B = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_INPUT = Font(name=FONT, size=11, bold=True, color="0000FF")
F_NOTE = Font(name=FONT, size=9, italic=True, color="595959")
FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_INPUT = PatternFill("solid", fgColor="FFFF00")
FILL_SUM = PatternFill("solid", fgColor="D9E1F2")
FILL_BAD = PatternFill("solid", fgColor="F8CBAD")
FILL_GOOD = PatternFill("solid", fgColor="C6EFCE")
THIN = Side(style="thin", color="BFBFBF")
NUM_TEUR = '#,##0,;[Red]-#,##0,;"–"'
NUM_PCT = '0.0%;[Red]-0.0%;"–"'
NUM_EUR = '#,##0;[Red]-#,##0;"–"'

KPI_ROWS = [  # key, label, kind (E = income: plus is good, K = cost: plus is bad), bold
    ("umsatz", "Umsatzerlöse", "E", False), ("nettoumsatz", "Nettoumsatz", "E", False),
    ("variable_kosten", "Variable Kosten", "K", False), ("db1", "Deckungsbeitrag I", "E", True),
    ("fixkosten_db2", "Fixkosten Produktgruppen/Fertigung", "K", False), ("db2", "Deckungsbeitrag II", "E", True),
    ("fixkosten_db3", "Bereichsfixkosten", "K", False), ("db3", "Deckungsbeitrag III", "E", True),
    ("unternehmensfixkosten", "Unternehmensfixkosten", "K", False), ("betriebsergebnis", "Betriebsergebnis", "E", True),
]
BRIDGE = [("plan_db2", "DB II Plan"), ("mengeneffekt", "Mengeneffekt"), ("mixeffekt", "Mixeffekt"),
          ("preiseffekt", "Preiseffekt"), ("materialkosteneffekt", "Materialkosteneffekt"),
          ("erloesschmaelerung", "Erlösschmälerungen"), ("fixkosteneffekt", "Fixkosteneffekt"),
          ("waehrungseffekt", "Währungseffekt"), ("ist_db2", "DB II Ist")]
PG_TEXT = {"PG10": "Kreiselpumpen", "PG20": "Dosierpumpen", "PG30": "Ventile und Armaturen",
           "PG40": "Ersatzteile", "PG50": "Service"}
RECALC = Path("/root/.claude/skills/synced/b404d8a9-0cb2-46d2-bf28-7dd54c87c45f_14772263-d609-40de-bfd5-2f2703f208fb"
              "/xlsx/scripts/recalc.py")


# ---------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------
def load_data(con) -> dict[str, pd.DataFrame]:
    kpi = con.execute("""select periode, jahr, monat, bereich, kennzahl, round(ist_eur, 2) as ist_eur,
                                round(plan_eur, 2) as plan_eur
                         from semantic.sem_kennzahlen_monat order by 1, 4, 5""").df()
    br = con.execute("select * from semantic.sem_abweichungsbruecke").df()
    cols = {"plan_db2": "plan_db2_eur", "mengeneffekt": "mengeneffekt_eur", "mixeffekt": "mixeffekt_eur",
            "preiseffekt": "preiseffekt_eur", "materialkosteneffekt": "materialkosteneffekt_eur",
            "erloesschmaelerung": "erloesschmaelerung_eur", "fixkosteneffekt": "fixkosteneffekt_db2_eur",
            "waehrungseffekt": "waehrungseffekt_eur", "ist_db2": "ist_db2_eur"}
    bridge = br.melt(id_vars=["jahr", "bis_monat", "bereich"], value_vars=list(cols.values()),
                     var_name="col", value_name="wert_eur")
    bridge["position"] = bridge["col"].map({v: k for k, v in cols.items()})
    bridge = bridge[["jahr", "bis_monat", "bereich", "position", "wert_eur"]]  # full precision: bridge closes
    pg = con.execute("""select jahr, bis_monat, bereich, produktgruppe, sum(ist_umsatz_eur) ist_umsatz_eur,
                               sum(plan_umsatz_eur) plan_umsatz_eur, sum(ist_db1_eur) ist_db1_eur,
                               sum(plan_db1_eur) plan_db1_eur, sum(preiseffekt_eur) preiseffekt_eur,
                               sum(mengeneffekt_eur) mengeneffekt_eur, sum(mixeffekt_eur) mixeffekt_eur,
                               sum(materialkosteneffekt_eur) materialkosteneffekt_eur
                        from semantic.sem_produktgruppen group by grouping sets
                             ((jahr, bis_monat, bereich, produktgruppe), (jahr, bis_monat, produktgruppe))
                        order by 1, 2, 3, 4""").df()
    pg["bereich"] = pg["bereich"].fillna("GRUPPE")
    con.execute("set variable planwerk_user = 'controller'")
    kst = con.execute("""select jahr, bis_monat, bereich, kostenstelle, kostenstelle_text, verantwortlich,
                                round(plan_eur, 2) plan_eur, round(ist_eur, 2) ist_eur, round(abweichung_eur, 2) abweichung_eur
                         from semantic.sem_kostenstellen order by 1, 2, 4""").df()
    # one current name per cost centre (SCD2 renames would otherwise split rows)
    names = con.execute("""select cost_centre, cost_centre_name, company_code, responsible from core.dim_cost_centre
                           where is_current""").df().set_index("cost_centre")
    kst = kst.groupby(["jahr", "bis_monat", "bereich", "kostenstelle"], as_index=False)[
        ["plan_eur", "ist_eur", "abweichung_eur"]].sum()
    kst["kostenstelle_text"] = kst["kostenstelle"].map(names["cost_centre_name"])
    kst["verantwortlich"] = kst["kostenstelle"].map(names["responsible"])
    kst["schluessel"] = kst["jahr"].astype(str) + "|" + kst["bis_monat"].astype(str) + "|" + kst["kostenstelle"]
    kst = kst[["schluessel", "jahr", "bis_monat", "bereich", "kostenstelle", "kostenstelle_text", "verantwortlich",
               "plan_eur", "ist_eur", "abweichung_eur"]]
    ccs = names.reset_index().sort_values("cost_centre")[["cost_centre", "cost_centre_name", "company_code"]]
    return dict(kpi=kpi, bridge=bridge, pg=pg, kst=kst, ccs=ccs)


def commentaries(con, year: int) -> pd.DataFrame:
    from planwerk.assistant.graph import Assistant
    from planwerk.assistant.llm import OfflineProvider

    a = Assistant(OfflineProvider(), con=con, audit_log=False)
    rows = []
    for scope in ("GRUPPE", "1000", "2000", "3000"):
        for m in range(1, 13):
            r = a.commentary(scope, year, m)
            if not r["verified"]:
                raise RuntimeError(f"commentary {scope} {m} failed verification: {r['unverified']}")
            text = re.sub(r"^### .*\n+", "", r["answer"]).replace("**", "").replace("_Simulierte Daten (Nordwerk GmbH)._", "")
            rows.append(dict(schluessel=f"{scope}|{year}|{m}", bereich=scope, monat=m, kommentar=text.strip()))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# workbook helpers
# ---------------------------------------------------------------------------------------------
def _header(ws, row: int, values: list[str], col: int = 1) -> None:
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=col + i, value=v)
        c.font, c.fill = F_H, FILL_H
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def _data_sheet(wb, name: str, df: pd.DataFrame, table: str, number_cols: dict[str, str]) -> None:
    ws = wb.create_sheet(name)
    _header(ws, 1, list(df.columns))
    for r in df.itertuples(index=False):
        ws.append([v.item() if hasattr(v, "item") else v for v in r])
    for j, col in enumerate(df.columns, start=1):
        ws.column_dimensions[get_column_letter(j)].width = max(12, min(40, len(col) + 4))
        fmt = number_cols.get(col)
        for row in ws.iter_rows(min_row=2, min_col=j, max_col=j):
            for c in row:
                c.font = F_B
                if fmt:
                    c.number_format = fmt
    ref = f"A1:{get_column_letter(len(df.columns))}{len(df) + 1}"
    t = Table(displayName=table, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes = "A2"


def _col(df: pd.DataFrame, name: str) -> str:
    return get_column_letter(list(df.columns).index(name) + 1)


# ---------------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------------
def build(data: dict, comments: pd.DataFrame, year: int, month: int, path: Path) -> list[str]:
    """Writes the workbook; returns the cells (sheet!coord) that get XVERWEIS injected."""
    wb = Workbook()
    cover = wb.active
    cover.title = "Deckblatt"
    kpi, bridge, pg, kst = data["kpi"], data["bridge"], data["pg"], data["kst"]

    # ---- cover / selectors --------------------------------------------------------------------
    cover["B2"] = "Monatsbericht Controlling – Nordwerk-Gruppe"
    cover["B2"].font = F_TITLE
    cover["B3"] = "SIMULIERTE DATEN – fiktive Nordwerk-Gruppe, keine echten Unternehmenszahlen."
    cover["B3"].font = Font(name=FONT, size=10, bold=True, color="C00000")
    labels = [("B5", "Berichtsjahr", "C5", year), ("B6", "Berichtsmonat (1–12)", "C6", month),
              ("B7", "Bereich (GRUPPE, 1000, 2000, 3000)", "C7", "GRUPPE")]
    for lc, text, vc, val in labels:
        cover[lc], cover[lc].font = text, F_BOLD
        cell = cover[vc]
        cell.value, cell.font, cell.fill = val, F_INPUT, FILL_INPUT
        cell.alignment = Alignment(horizontal="center")
        cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
    cover["C7"].number_format = "@"
    cover["D5"] = "← Eingabe: gelbe Zellen ändern, alle Berichtsblätter rechnen neu."
    cover["D5"].font = F_NOTE
    dv_y = DataValidation(type="list", formula1='"2023,2024,2025"', allow_blank=False)
    dv_m = DataValidation(type="whole", operator="between", formula1="1", formula2="12")
    dv_b = DataValidation(type="list", formula1='"GRUPPE,1000,2000,3000"', allow_blank=False)
    for dv, ref in ((dv_y, "C5"), (dv_m, "C6"), (dv_b, "C7")):
        cover.add_data_validation(dv)
        dv.add(ref)
    cover["B9"], cover["B9"].font = "Bereich", F_BOLD
    cover["C9"] = ('=IF(C7="GRUPPE","Nordwerk-Gruppe (konsolidiert)",IF(C7="1000","Nordwerk GmbH (DE)",'
                   'IF(C7="2000","Nordwerk Austria GmbH (AT)","Nordwerk Polska Sp. z o.o. (PL)")))')
    cover["B10"], cover["B10"].font = "Berichtszeitraum", F_BOLD
    cover["C10"] = ('=INDEX({"Januar","Februar","März","April","Mai","Juni","Juli","August","September",'
                    '"Oktober","November","Dezember"},C6)&" "&C5')
    for c in ("C9", "C10"):
        cover[c].font = F_B
    for n, ref in (("Jahr", "$C$5"), ("Monat", "$C$6"), ("Bereich", "$C$7"), ("BereichText", "$C$9"),
                   ("Zeitraum", "$C$10")):
        wb.defined_names[n] = DefinedName(n, attr_text=f"Deckblatt!{ref}")
    cover["B12"], cover["B12"].font = "Inhalt", F_BOLD
    toc = [("DB-Rechnung", "Mehrstufige Deckungsbeitragsrechnung: Monat, kumuliert, Vorjahr"),
           ("Abweichungsbrücke", "Plan-Ist-Brücke DB II (Menge, Mix, Preis, Kosten, Währung)"),
           ("Produktgruppen", "Umsatz, DB I und Effekte je Produktgruppe, kumuliert"),
           ("Kostenstellen", "Primärkostenabweichung je Kostenstelle, kumuliert"),
           ("Kommentar", "Monatskommentar (KI-Entwurf, jede Zahl geprüft; 2025)"),
           ("XVERWEIS", "Schnellabfrage Kostenstelle mit XVERWEIS"),
           ("Power Query", "M-Code zum Aktualisieren der Datenblätter"), ("Legende", "Hinweise, Vorzeichen, Pivot")]
    for i, (sheet, desc) in enumerate(toc):
        c = cover.cell(row=13 + i, column=2, value=sheet)
        c.hyperlink, c.font = f"#'{sheet}'!A1", Font(name=FONT, size=10, color="0563C1", underline="single")
        cover.cell(row=13 + i, column=3, value=desc).font = F_B
    cover.column_dimensions["A"].width = 3
    cover.column_dimensions["B"].width = 36
    cover.column_dimensions["C"].width = 34
    cover.column_dimensions["D"].width = 50
    cover.sheet_view.showGridLines = False

    # ---- data sheets (tables) -----------------------------------------------------------------
    _data_sheet(wb, "Daten_KPI", kpi, "tbl_KPI", {"ist_eur": NUM_EUR, "plan_eur": NUM_EUR})
    _data_sheet(wb, "Daten_Bruecke", bridge, "tbl_Bruecke", {"wert_eur": NUM_EUR})
    _data_sheet(wb, "Daten_PG", pg, "tbl_PG", {c: NUM_EUR for c in pg.columns if c.endswith("_eur")})
    _data_sheet(wb, "Daten_KSt", kst, "tbl_KSt", {c: NUM_EUR for c in kst.columns if c.endswith("_eur")})
    _data_sheet(wb, "Daten_Kommentar", comments, "tbl_Kommentar", {})
    wb["Daten_Kommentar"].column_dimensions["D"].width = 120
    nk = len(kpi) + 1

    def K(col: str) -> str:  # absolute column range in Daten_KPI
        c = _col(kpi, col)
        return f"Daten_KPI!${c}$2:${c}${nk}"

    # ---- DB-Rechnung ---------------------------------------------------------------------------
    ws = wb.create_sheet("DB-Rechnung", 1)
    ws["B2"] = '="Deckungsbeitragsrechnung – "&BereichText'
    ws["B2"].font = F_TITLE
    ws["B3"] = '="Berichtsmonat "&Zeitraum&" · Werte in TEUR · Abweichung = Ist − Plan"'
    ws["B3"].font = F_NOTE
    _header(ws, 5, ["Schlüssel", "Position", "Art", "Ist Monat", "Plan Monat", "Abw. Monat", "Abw. %",
                    "Ist kumuliert", "Plan kumuliert", "Abw. kumuliert", "Abw. %", "Vorjahr kum.", "Veränd. VJ %"])
    for i, (key, label, kind, bold) in enumerate(KPI_ROWS):
        r = 6 + i
        ws.cell(r, 1, key)
        ws.cell(r, 2, label)
        ws.cell(r, 3, kind)
        base = f'{K("bereich")},Bereich,{K("kennzahl")},$A{r},{K("jahr")}'
        ws.cell(r, 4, f'=SUMIFS({K("ist_eur")},{base},Jahr,{K("monat")},Monat)')
        ws.cell(r, 5, f'=SUMIFS({K("plan_eur")},{base},Jahr,{K("monat")},Monat)')
        ws.cell(r, 6, f"=D{r}-E{r}")
        ws.cell(r, 7, f'=IF(E{r}=0,"",F{r}/ABS(E{r}))')
        ws.cell(r, 8, f'=SUMIFS({K("ist_eur")},{base},Jahr,{K("monat")},"<="&Monat)')
        ws.cell(r, 9, f'=SUMIFS({K("plan_eur")},{base},Jahr,{K("monat")},"<="&Monat)')
        ws.cell(r, 10, f"=H{r}-I{r}")
        ws.cell(r, 11, f'=IF(I{r}=0,"",J{r}/ABS(I{r}))')
        ws.cell(r, 12, f'=SUMIFS({K("ist_eur")},{base},Jahr-1,{K("monat")},"<="&Monat)')
        ws.cell(r, 13, f'=IF(L{r}=0,"",H{r}/L{r}-1)')
        for c in range(1, 14):
            cell = ws.cell(r, c)
            cell.font = F_BOLD if bold else F_B
            if bold:
                cell.fill = FILL_SUM
            cell.border = Border(bottom=THIN)
            if c in (4, 5, 6, 8, 9, 10, 12):
                cell.number_format = NUM_TEUR
            elif c in (7, 11, 13):
                cell.number_format = NUM_PCT
    last = 6 + len(KPI_ROWS) - 1
    for col in ("F", "J"):  # favourable / unfavourable colouring by account kind
        rng = f"{col}6:{col}{last}"
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'OR(AND($C6="E",{col}6<-0.5),AND($C6="K",{col}6>0.5))'], fill=FILL_BAD))
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'OR(AND($C6="E",{col}6>0.5),AND($C6="K",{col}6<-0.5))'], fill=FILL_GOOD))
    chk = last + 2
    ws.cell(chk, 2, "Kontrolle: DB I − Fixkosten Fertigung − DB II (muss 0 sein)").font = F_NOTE
    ws.cell(chk, 8, "=H9-H10-H11").number_format = NUM_EUR
    ws.cell(chk + 1, 2, "Kontrolle: Nettoumsatz − variable Kosten − DB I (muss 0 sein)").font = F_NOTE
    ws.cell(chk + 1, 8, "=H7-H8-H9").number_format = NUM_EUR
    ws.cell(chk + 3, 2, "Grün = günstig, rot = ungünstig (Erlöse: Ist über Plan günstig; Kosten: Ist unter Plan günstig).").font = F_NOTE
    ws.column_dimensions["A"].hidden = True
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 6
    for c in range(4, 14):
        ws.column_dimensions[get_column_letter(c)].width = 13
    ws.freeze_panes = "D6"
    ws.sheet_view.showGridLines = False
    chart = BarChart()
    chart.type, chart.title, chart.y_axis.title = "col", "Ist vs. Plan kumuliert (TEUR)", "TEUR"
    chart.y_axis.number_format = "#,##0,"
    chart.y_axis.delete = False
    chart.x_axis.delete = False
    chart.add_data(Reference(ws, min_col=8, max_col=9, min_row=5, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=2, min_row=6, max_row=last))
    chart.height, chart.width = 8, 22
    ws.add_chart(chart, f"B{chk + 5}")

    # ---- Abweichungsbrücke --------------------------------------------------------------------
    wsb = wb.create_sheet("Abweichungsbrücke", 2)
    nb = len(bridge) + 1

    def B(col: str) -> str:
        c = _col(bridge, col)
        return f"Daten_Bruecke!${c}$2:${c}${nb}"

    wsb["B2"] = '="Abweichungsbrücke DB II – "&BereichText'
    wsb["B2"].font = F_TITLE
    wsb["B3"] = '="Januar bis "&Zeitraum&" · TEUR · positiv = günstig für den DB II"'
    wsb["B3"].font = F_NOTE
    _header(wsb, 5, ["Schlüssel", "Position", "Wert (TEUR)", "Kumuliert (TEUR)", "Anteil an Abweichung"])
    for i, (key, label) in enumerate(BRIDGE):
        r = 6 + i
        wsb.cell(r, 1, key)
        wsb.cell(r, 2, label).font = F_BOLD if key in ("plan_db2", "ist_db2") else F_B
        wsb.cell(r, 3, f'=SUMIFS({B("wert_eur")},{B("jahr")},Jahr,{B("bis_monat")},Monat,{B("bereich")},Bereich,'
                       f'{B("position")},$A{r})').number_format = NUM_TEUR
        wsb.cell(r, 4, "=C6" if i == 0 else (f"=C{r}" if key == "ist_db2" else f"=D{r - 1}+C{r}")).number_format = NUM_TEUR
        if key not in ("plan_db2", "ist_db2"):
            wsb.cell(r, 5, f'=IF($C$14-$C$6=0,"",C{r}/($C$14-$C$6))').number_format = NUM_PCT
        for c in range(2, 6):
            wsb.cell(r, c).border = Border(bottom=THIN)
            if key in ("plan_db2", "ist_db2"):
                wsb.cell(r, c).fill = FILL_SUM
    wsb.conditional_formatting.add("C7:C13", FormulaRule(formula=["C7<-0.5"], fill=FILL_BAD))
    wsb.conditional_formatting.add("C7:C13", FormulaRule(formula=["C7>0.5"], fill=FILL_GOOD))
    wsb["B16"] = "Kontrolle: Plan + Summe Effekte − Ist (muss 0 sein)"
    wsb["B16"].font = F_NOTE
    wsb["C16"] = "=C6+SUM(C7:C13)-C14"
    wsb["C16"].number_format = '#,##0.00;[Red]-#,##0.00;"0,00"'
    wsb["B17"] = "Abweichung DB II gesamt"
    wsb["B17"].font = F_BOLD
    wsb["C17"] = "=C14-C6"
    wsb["C17"].number_format = NUM_TEUR
    wsb["D17"] = '=IF(C6=0,"",C17/ABS(C6))'
    wsb["D17"].number_format = NUM_PCT
    wsb.column_dimensions["A"].hidden = True
    wsb.column_dimensions["B"].width = 34
    for c in "CDE":
        wsb.column_dimensions[c].width = 18
    wsb.sheet_view.showGridLines = False
    bc = BarChart()
    bc.type, bc.title = "bar", "Effekte auf den DB II (TEUR, positiv = günstig)"
    bc.add_data(Reference(wsb, min_col=3, min_row=7, max_row=13), titles_from_data=False)
    bc.set_categories(Reference(wsb, min_col=2, min_row=7, max_row=13))
    bc.legend = None
    bc.y_axis.number_format = "#,##0,"
    bc.y_axis.delete = False
    bc.x_axis.delete = False
    bc.x_axis.tickLblPos = "low"
    bc.height, bc.width = 8, 18
    wsb.add_chart(bc, "B20")

    # ---- Produktgruppen ------------------------------------------------------------------------
    wsp = wb.create_sheet("Produktgruppen", 3)
    npg = len(pg) + 1

    def P(col: str) -> str:
        c = _col(pg, col)
        return f"Daten_PG!${c}$2:${c}${npg}"

    wsp["B2"] = '="Produktgruppen – "&BereichText'
    wsp["B2"].font = F_TITLE
    wsp["B3"] = ('="Januar bis "&Zeitraum&" · TEUR · konstante Währung (Planwechselkurse), vor Skonti · '
                 'Effekte positiv = günstig"')
    wsp["B3"].font = F_NOTE
    heads = ["PG", "Produktgruppe", "Umsatz Ist", "Umsatz Plan", "Abw. Umsatz", "DB I Ist", "DB I Plan", "Abw. DB I",
             "Preiseffekt", "Mengeneffekt", "Mixeffekt", "Materialkosten­effekt"]
    _header(wsp, 5, heads)
    src = ["ist_umsatz_eur", "plan_umsatz_eur", None, "ist_db1_eur", "plan_db1_eur", None, "preiseffekt_eur",
           "mengeneffekt_eur", "mixeffekt_eur", "materialkosteneffekt_eur"]
    for i, (g, text) in enumerate(PG_TEXT.items()):
        r = 6 + i
        wsp.cell(r, 1, g).font = F_B
        wsp.cell(r, 2, text).font = F_B
        for j, s in enumerate(src):
            c = 3 + j
            if s is None:
                f = f"={get_column_letter(c - 2)}{r}-{get_column_letter(c - 1)}{r}"
            else:
                f = (f'=SUMIFS({P(s)},{P("jahr")},Jahr,{P("bis_monat")},Monat,{P("bereich")},Bereich,'
                     f'{P("produktgruppe")},$A{r})')
            cell = wsp.cell(r, c, f)
            cell.number_format, cell.font, cell.border = NUM_TEUR, F_B, Border(bottom=THIN)
    tr = 6 + len(PG_TEXT)
    wsp.cell(tr, 2, "Summe").font = F_BOLD
    for c in range(3, 13):
        L = get_column_letter(c)
        cell = wsp.cell(tr, c, f"=SUM({L}6:{L}{tr - 1})")
        cell.number_format, cell.font, cell.fill = NUM_TEUR, F_BOLD, FILL_SUM
    wsp.conditional_formatting.add(f"E6:L{tr - 1}", FormulaRule(formula=["E6<-0.5"], fill=FILL_BAD))
    wsp.conditional_formatting.add(f"E6:L{tr - 1}", FormulaRule(formula=["E6>0.5"], fill=FILL_GOOD))
    wsp.cell(tr + 2, 2, "Kontrolle: Abw. DB I − Summe der vier Effekte (muss 0 sein)").font = F_NOTE
    cell = wsp.cell(tr + 2, 8, f"=H{tr}-SUM(I{tr}:L{tr})")
    cell.number_format = '#,##0.00;[Red]-#,##0.00;"0,00"'
    wsp.column_dimensions["B"].width = 24
    for c in range(3, 13):
        wsp.column_dimensions[get_column_letter(c)].width = 13
    wsp.sheet_view.showGridLines = False

    # ---- Kostenstellen ------------------------------------------------------------------------
    wsk = wb.create_sheet("Kostenstellen", 4)
    nks = len(kst) + 1

    def S(col: str) -> str:
        c = _col(kst, col)
        return f"Daten_KSt!${c}$2:${c}${nks}"

    wsk["B2"] = '="Kostenstellen – "&BereichText'
    wsk["B2"].font = F_TITLE
    wsk["B3"] = '="Primärkosten Januar bis "&Zeitraum&" · TEUR · Abweichung = Plan − Ist (positiv = günstig)"'
    wsk["B3"].font = F_NOTE
    _header(wsk, 5, ["Kostenstelle", "Bezeichnung", "Gesellschaft", "Plan", "Ist", "Abweichung", "Abw. %", "Im Bereich"])
    ccs = data["ccs"]
    for i, cc in enumerate(ccs.itertuples(index=False)):
        r = 6 + i
        wsk.cell(r, 1, cc.cost_centre)
        wsk.cell(r, 2, cc.cost_centre_name)
        wsk.cell(r, 3, cc.company_code)
        wsk.cell(r, 8, f'=OR(Bereich="GRUPPE",C{r}=Bereich)')
        for j, s in enumerate(("plan_eur", "ist_eur", "abweichung_eur")):
            wsk.cell(r, 4 + j, f'=IF($H{r},SUMIFS({S(s)},{S("jahr")},Jahr,{S("bis_monat")},Monat,'
                               f'{S("kostenstelle")},$A{r}),0)').number_format = NUM_TEUR
        wsk.cell(r, 7, f'=IF(D{r}=0,"",F{r}/ABS(D{r}))').number_format = NUM_PCT
        for c in range(1, 9):
            wsk.cell(r, c).font = F_B
            wsk.cell(r, c).border = Border(bottom=THIN)
    kr = 6 + len(ccs)
    wsk.cell(kr, 2, "Summe Bereich").font = F_BOLD
    for c in (4, 5, 6):
        L = get_column_letter(c)
        cell = wsk.cell(kr, c, f"=SUM({L}6:{L}{kr - 1})")
        cell.number_format, cell.font, cell.fill = NUM_TEUR, F_BOLD, FILL_SUM
    wsk.conditional_formatting.add(f"F6:F{kr - 1}", FormulaRule(formula=["F6<-5000"], fill=FILL_BAD))
    wsk.conditional_formatting.add(f"A6:G{kr - 1}", FormulaRule(formula=["NOT($H6)"],
                                                                 font=Font(name=FONT, color="BFBFBF")))
    wsk.cell(kr + 2, 2, "Rot: ungünstige Abweichung über 5 TEUR (Wesentlichkeitsschwelle). "
                        "Grau: Kostenstelle gehört nicht zum gewählten Bereich.").font = F_NOTE
    wsk.column_dimensions["B"].width = 34
    for c in "ACDEFGH":
        wsk.column_dimensions[c].width = 13
    wsk.freeze_panes = "A6"
    wsk.sheet_view.showGridLines = False

    # ---- Kommentar ----------------------------------------------------------------------------
    wsc = wb.create_sheet("Kommentar", 5)
    nc = len(comments) + 1
    wsc["B2"] = '="Monatskommentar – "&BereichText&", "&Zeitraum'
    wsc["B2"].font = F_TITLE
    wsc["B3"] = ("KI-Entwurf des Planwerk-Assistenten: jede Zahl stammt aus SQL und wurde automatisch gegen das "
                 "Faktenblatt geprüft. Vor Versand vom Controlling freizugeben.")
    wsc["B3"].font = F_NOTE
    wsc["B5"] = (f'=IFERROR(INDEX(Daten_Kommentar!$D$2:$D${nc},MATCH(Bereich&"|"&Jahr&"|"&Monat,'
                 f'Daten_Kommentar!$A$2:$A${nc},0)),"Für diesen Zeitraum liegt kein Kommentar vor (Kommentare: '
                 f'Januar bis Dezember {year}).")')
    wsc["B5"].font = Font(name=FONT, size=11)
    wsc["B5"].alignment = Alignment(wrap_text=True, vertical="top")
    wsc.merge_cells("B5:L40")
    wsc.column_dimensions["A"].width = 3
    for c in range(2, 13):
        wsc.column_dimensions[get_column_letter(c)].width = 14
    wsc.sheet_view.showGridLines = False

    # ---- XVERWEIS ------------------------------------------------------------------------------
    wsx = wb.create_sheet("XVERWEIS", 6)
    wsx["B2"] = "Schnellabfrage Kostenstelle (XVERWEIS)"
    wsx["B2"].font = F_TITLE
    wsx["B3"] = ("Kostenstelle in die gelbe Zelle eintragen. Spalte C nutzt XVERWEIS (Excel 365), Spalte D die "
                 "gleiche Abfrage mit INDEX/VERGLEICH als Kontrolle und für ältere Excel-Versionen.")
    wsx["B3"].font = F_NOTE
    wsx["B5"], wsx["B5"].font = "Kostenstelle", F_BOLD
    wsx["C5"] = "1410"
    wsx["C5"].font, wsx["C5"].fill, wsx["C5"].number_format = F_INPUT, FILL_INPUT, "@"
    wsx["C5"].comment = Comment("Beispiel: 1410 (Instandhaltung). Liste der Kostenstellen im Blatt Kostenstellen.",
                                "Planwerk")
    wsx["B6"], wsx["B6"].font = "Schlüssel", F_BOLD
    wsx["C6"] = '=Jahr&"|"&Monat&"|"&C5'
    _header(wsx, 8, ["", "Feld", "XVERWEIS", "INDEX/VERGLEICH (Kontrolle)"], col=1)
    fields = [("Bezeichnung", "kostenstelle_text", None), ("Verantwortlich", "verantwortlich", None),
              ("Plan kumuliert", "plan_eur", NUM_TEUR), ("Ist kumuliert", "ist_eur", NUM_TEUR),
              ("Abweichung (Plan − Ist)", "abweichung_eur", NUM_TEUR)]
    keycol = f"Daten_KSt!$A$2:$A${nks}"
    inject = []
    for i, (label, col, fmt) in enumerate(fields):
        r = 9 + i
        wsx.cell(r, 2, label).font = F_B
        ret = f"Daten_KSt!${_col(kst, col)}$2:${_col(kst, col)}${nks}"
        idx = f'=IFERROR(INDEX({ret},MATCH($C$6,{keycol},0)),"nicht gefunden")'
        wsx.cell(r, 3, idx)  # replaced by XVERWEIS after recalculation (same cached value)
        wsx.cell(r, 4, idx)
        inject.append((f"C{r}", f'_xlfn.XLOOKUP($C$6,{keycol},{ret},"nicht gefunden")'))
        for c in (3, 4):
            wsx.cell(r, c).font = F_B
            if fmt:
                wsx.cell(r, c).number_format = fmt
    wsx["B15"] = "Kontrolle: XVERWEIS = INDEX/VERGLEICH"
    wsx["B15"].font = F_NOTE
    wsx["C15"] = '=IF(AND(C9=D9,C10=D10,C11=D11,C12=D12,C13=D13),"OK","Abweichung")'
    wsx.column_dimensions["B"].width = 28
    wsx.column_dimensions["C"].width = 30
    wsx.column_dimensions["D"].width = 30
    wsx.sheet_view.showGridLines = False

    # ---- Power Query ----------------------------------------------------------------------------
    wsq = wb.create_sheet("Power Query", 7)
    wsq["B2"] = "Power Query: Datenblätter aktualisieren"
    wsq["B2"].font = F_TITLE
    steps = [
        "1. Daten > Daten abrufen > Leere Abfrage > Erweiterter Editor: den M-Code unten einfügen.",
        "2. Parameter pOrdner auf den Ordner mit den CSV-Dateien setzen (wird mit dem Bericht erzeugt: daten/).",
        "3. Abfrage 'KPI' laden in: vorhandene Tabelle tbl_KPI (Blatt Daten_KPI). Gleiches Muster für Bruecke, PG, KSt.",
        "4. Daten > Alle aktualisieren. Die Berichtsblätter rechnen automatisch neu.",
    ]
    for i, s in enumerate(steps):
        wsq.cell(4 + i, 2, s).font = F_B
    m_code = """let
    pOrdner = "C:\\Planwerk\\daten\\",
    Quelle = Csv.Document(File.Contents(pOrdner & "kpi.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Kopf = Table.PromoteHeaders(Quelle, [PromoteAllScalars = true]),
    Typen = Table.TransformColumnTypes(Kopf, {
        {"periode", type text}, {"jahr", Int64.Type}, {"monat", Int64.Type}, {"bereich", type text},
        {"kennzahl", type text}, {"ist_eur", type number}, {"plan_eur", type number}}, "en-US"),
    Sortiert = Table.Sort(Typen, {{"periode", Order.Ascending}, {"bereich", Order.Ascending}})
in
    Sortiert"""
    wsq["B9"] = "M-Code (Abfrage KPI):"
    wsq["B9"].font = F_BOLD
    for i, line in enumerate(m_code.splitlines()):
        wsq.cell(10 + i, 2, line).font = Font(name="Consolas", size=10)
    wsq.column_dimensions["B"].width = 140
    wsq.sheet_view.showGridLines = False

    # ---- Legende -------------------------------------------------------------------------------
    wsl = wb.create_sheet("Legende", 8)
    wsl["B2"] = "Legende und Hinweise"
    wsl["B2"].font = F_TITLE
    notes = [
        ("Daten", "Simulierte Daten der fiktiven Nordwerk-Gruppe (Generator Seed 42). Quelle: "
                  "Planwerk-Warehouse, semantische Sichten semantic.sem_*."),
        ("Eingaben", "Nur die gelben Zellen (Deckblatt C5:C7, XVERWEIS C5) ändern; alle anderen Zellen sind Formeln."),
        ("Einheit", "Berichtsblätter in TEUR (Zahlenformat), Datenblätter in EUR. Konzernwährung EUR; PL zu ECB-Monatskursen."),
        ("Vorzeichen", "DB-Rechnung: Abweichung = Ist − Plan. Brücke und Kostenstellen: positiv = günstig."),
        ("Brücke", "Mengeneffekt zu Planpreisen, Mix, Preis, Materialkosten, Erlösschmälerungen, Fixkosten, Währung; "
                   "die Brücke schließt exakt (Kontrollzeile)."),
        ("Pivot", "Die Datenblätter sind Excel-Tabellen (tbl_KPI, tbl_Bruecke, tbl_PG, tbl_KSt): Einfügen > "
                  "PivotTable > Tabelle/Bereich tbl_KPI, Zeilen: kennzahl, Spalten: jahr, Werte: Summe ist_eur."),
        ("Kommentar", "Monatskommentare sind KI-Entwürfe mit geprüften Zahlen; Verantwortung für den Versand trägt das Controlling."),
        ("Erzeugt", "python -m planwerk.reporting.excel_report (Planwerk)."),
    ]
    for i, (k, v) in enumerate(notes):
        wsl.cell(4 + i, 2, k).font = F_BOLD
        c = wsl.cell(4 + i, 3, v)
        c.font, c.alignment = F_B, Alignment(wrap_text=True, vertical="top")
        wsl.row_dimensions[4 + i].height = 30
    wsl.column_dimensions["B"].width = 14
    wsl.column_dimensions["C"].width = 110
    wsl.sheet_view.showGridLines = False

    for name in ("Deckblatt", "DB-Rechnung", "Abweichungsbrücke", "Produktgruppen", "Kostenstellen"):
        wb[name].page_setup.orientation = "landscape"
        wb[name].page_setup.fitToWidth = 1
        wb[name].sheet_properties.pageSetUpPr.fitToPage = True
    for name in ("Daten_KPI", "Daten_Bruecke", "Daten_PG", "Daten_KSt", "Daten_Kommentar"):
        wb[name].sheet_properties.tabColor = "A6A6A6"
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    return [("XVERWEIS", cell, f) for cell, f in inject]


def _recalc(path: Path) -> dict:
    out = subprocess.run([sys.executable, str(RECALC), str(path), "120"], capture_output=True, text=True)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"recalc failed: {out.stdout} {out.stderr}") from e


def _inject_xlookup(path: Path, cells: list[tuple[str, str, str]]) -> None:
    """Replace the formula text of the given cells by XLOOKUP, keeping LibreOffice's cached value."""
    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path) as zin:
        wbxml = zin.read("xl/workbook.xml").decode()
        rels = zin.read("xl/_rels/workbook.xml.rels").decode()
        rid = re.search(r'<sheet[^>]*name="XVERWEIS"[^>]*r:id="(rId\d+)"', wbxml).group(1)
        target = re.search(rf'Id="{rid}"[^>]*Target="([^"]+)"|Target="([^"]+)"[^>]*Id="{rid}"', rels)
        sheet = "xl/" + (target.group(1) or target.group(2)).lstrip("/").removeprefix("xl/")
        xml = zin.read(sheet).decode()
        for _, cell, formula in cells:
            pat = re.compile(rf'(<c r="{cell}"[^>]*>)<f[^>]*>[^<]*</f>')
            esc = "<f>" + formula.replace("&", "&amp;").replace('"', "&quot;") + "</f>"
            xml, n = pat.subn(lambda m, esc=esc: m.group(1) + esc, xml)
            if n != 1:
                raise RuntimeError(f"could not inject XLOOKUP into {cell}")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = xml.encode() if item.filename == sheet else zin.read(item.filename)
                zout.writestr(item, data)
    shutil.move(tmp, path)


def write_csv(data: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("kpi", "bridge", "pg", "kst"):
        data[name].to_csv(folder / f"{name}.csv", sep=";", index=False, encoding="utf-8")


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--month", type=int, default=12)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "out")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    con = connect()
    data = load_data(con)
    comments = commentaries(con, a.year)
    path = a.out / f"Monatsbericht_Nordwerk_{a.year}-{a.month:02d}.xlsx"
    cells = build(data, comments, a.year, a.month, path)
    res = _recalc(path)
    if res.get("status") != "success":
        raise RuntimeError(f"formula errors: {res}")
    _inject_xlookup(path, cells)
    write_csv(data, a.out / "daten")
    print(f"wrote {path} ({res['total_formulas']} formulas, 0 errors)")
    return path


if __name__ == "__main__":
    main()
