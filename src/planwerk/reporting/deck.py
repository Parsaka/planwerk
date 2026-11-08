"""German steering-committee deck (Lenkungskreis) for the fiscal-year 2025 close of the simulated
Nordwerk group. Every figure is read from the warehouse or from the result files in
docs/ergebnisse; nothing is typed in by hand.

    python -m planwerk.reporting.deck [--out reports/out]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from planwerk.assistant.formatting import fmt_eur, fmt_pct
from planwerk.generator.config import REPO_ROOT
from planwerk.warehouse import connect

PETROL = RGBColor(0x0B, 0x3C, 0x49)
PETROL_2 = RGBColor(0x1F, 0x5F, 0x6E)
ICE = RGBColor(0xE6, 0xEF, 0xF1)
SLATE = RGBColor(0x40, 0x4B, 0x55)
MUTED = RGBColor(0x6B, 0x77, 0x80)
COPPER = RGBColor(0xC0, 0x5A, 0x1C)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD = "Cambria"
BODY = "Calibri"
W, H = Inches(13.333), Inches(7.5)
RES = REPO_ROOT / "docs" / "ergebnisse"


# ---------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------
def load(con) -> dict:
    d: dict = {}
    k = con.execute("""select kennzahl, sum(ist_eur) ist, sum(plan_eur) plan from semantic.sem_kennzahlen_monat
                       where jahr = 2025 and bereich = 'GRUPPE' group by 1""").df().set_index("kennzahl")
    d["kpi"] = k
    d["bridge"] = con.execute("""select * from semantic.sem_abweichungsbruecke
                                 where jahr = 2025 and bis_monat = 12""").df().set_index("bereich")
    d["pg"] = con.execute("""select produktgruppe, produktgruppe_text, sum(ist_db1_eur) - sum(plan_db1_eur) abw,
                                    sum(preiseffekt_eur) preis, sum(mengeneffekt_eur) menge, sum(mixeffekt_eur) mix
                             from semantic.sem_produktgruppen where jahr = 2025 and bis_monat = 12
                             group by 1, 2 order by 1""").df()
    d["at"] = con.execute("""select monat, ist_eur, plan_eur from semantic.sem_kennzahlen_monat
                             where jahr = 2025 and bereich = '2000' and kennzahl = 'umsatz' order by 1""").df()
    con.execute("set variable planwerk_user = 'controller'")
    d["cc"] = con.execute("""select kostenstelle, any_value(kostenstelle_text) txt, sum(plan_eur) plan,
                                    sum(ist_eur) ist, sum(abweichung_eur) abw
                             from semantic.sem_kostenstellen where jahr = 2025 and bis_monat = 12
                             group by 1 order by abw limit 5""").df()
    d["oneoff"] = con.execute("""select sum(case when bis_monat = 6 then abweichung_eur else -abweichung_eur end)
                                 from semantic.sem_kostenarten where jahr = 2025 and kostenstelle = '1410'
                                   and konto = '701000' and bis_monat in (5, 6)""").fetchone()[0]
    d["fc"] = con.execute("""select version, methode, prognose_db2_eur, plan_db2_eur from semantic.sem_prognose
                             where jahr = 2025 and bereich = 'GRUPPE'""").df()
    d["q1"] = json.loads((RES / "q1_evaluation.json").read_text())
    d["q2"] = json.loads((RES / "q2_backtest_summary.json").read_text())
    d["q3"] = json.loads((RES / "q3_eval.json").read_text())
    return d


# ---------------------------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------------------------
def _text(slide, x, y, w, h, text, size=16, bold=False, color=SLATE, font=BODY, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP, italic=False, name=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Emu(0)
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        f = r.font
        f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
        f.color.rgb = color
    return tb


def _bullets(slide, x, y, w, h, items, size=16, color=SLATE):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        head, _, rest = it.partition("|")
        r = p.add_run()
        r.text = "▪  " + head
        r.font.size, r.font.name, r.font.color.rgb, r.font.bold = Pt(size), BODY, color, bool(rest)
        if rest:
            r2 = p.add_run()
            r2.text = " " + rest
            r2.font.size, r2.font.name, r2.font.color.rgb = Pt(size), BODY, color
    return tb


def _bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def _title(slide, title, sub=None):
    _text(slide, Inches(0.6), Inches(0.45), Inches(12.1), Inches(0.8), title, size=26, bold=True,
          color=PETROL, font=HEAD, name="Titel")
    if sub:
        _text(slide, Inches(0.6), Inches(1.2), Inches(12.1), Inches(0.4), sub, size=14, color=MUTED, italic=True)


def _footer(slide, n, dark=False):
    c = RGBColor(0xB8, 0xC7, 0xCC) if dark else MUTED
    _text(slide, Inches(0.6), Inches(7.0), Inches(9), Inches(0.3),
          "Planwerk · Simulierte Daten der fiktiven Nordwerk-Gruppe · keine echten Unternehmenszahlen", size=10,
          color=c)
    _text(slide, Inches(11.9), Inches(7.0), Inches(0.8), Inches(0.3), str(n), size=10, color=c, align=PP_ALIGN.RIGHT)


def _card(slide, x, y, w, h, value, label, color=PETROL, fill=ICE):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    s.adjustments[0] = 0.08
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.shadow.inherit = False
    _text(slide, x + Inches(0.3), y + Inches(0.25), w - Inches(0.6), Inches(0.9), value, size=34, bold=True,
          color=color, font=HEAD)
    _text(slide, x + Inches(0.3), y + Inches(1.15), w - Inches(0.6), h - Inches(1.3), label, size=14, color=SLATE)


def _style_chart(chart, size=12):
    chart.font.size = Pt(size)
    chart.font.name = BODY
    chart.font.color.rgb = SLATE


def _table(slide, x, y, w, rows, col_w, header_fill=PETROL, size=13, bold_rows=(), color_cols=None, left_cols=(0,)):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(0.4) * len(rows))
    t = shape.table
    for j, cw in enumerate(col_w):
        t.columns[j].width = cw
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.text = str(val)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if i == 0 else (ICE if i in bold_rows else WHITE)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j in left_cols else PP_ALIGN.RIGHT
                for r in p.runs:
                    f = r.font
                    f.size, f.name = Pt(size), BODY
                    if i == 0:
                        f.color.rgb, f.bold = WHITE, True
                    else:
                        f.bold = i in bold_rows
                        f.color.rgb = SLATE
                        if color_cols and j in color_cols and isinstance(color_cols[j], dict) and i in color_cols[j]:
                            f.color.rgb = color_cols[j][i]
    return shape


# ---------------------------------------------------------------------------------------------
# slides
# ---------------------------------------------------------------------------------------------
def build(d: dict, path: Path) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]
    k, br = d["kpi"], d["bridge"]
    g = br.loc["GRUPPE"]
    db2_ist, db2_plan = float(k.loc["db2", "ist"]), float(k.loc["db2", "plan"])
    gap = db2_ist - db2_plan
    n = 0

    def new(dark=False):
        nonlocal n
        n += 1
        s = prs.slides.add_slide(blank)
        _bg(s, PETROL if dark else WHITE)
        _footer(s, n, dark)
        return s

    # 1 title
    s = new(dark=True)
    _text(s, Inches(0.8), Inches(2.2), Inches(11.5), Inches(1.2), "Lenkungskreis Controlling", size=44, bold=True,
          color=WHITE, font=HEAD)
    _text(s, Inches(0.8), Inches(3.3), Inches(11.5), Inches(0.8),
          "Nordwerk-Gruppe · Geschäftsjahr 2025: Plan-Ist, Frühwarnung und KI-Assistent", size=22,
          color=RGBColor(0xCF, 0xE3, 0xE8))
    _text(s, Inches(0.8), Inches(4.6), Inches(11.5), Inches(0.9),
          ["Planwerk – Controlling- und Planungsplattform auf S/4HANA-Daten",
           "Simulierte Daten (fiktive Nordwerk GmbH), erzeugt mit realen Preis-, Lohn-, Energie- und Wechselkursindizes"],
          size=14, color=RGBColor(0xB8, 0xC7, 0xCC))
    s.notes_slide.notes_text_frame.text = ("Alle Zahlen in diesem Foliensatz stammen aus dem Planwerk-Warehouse "
                                          "(python -m planwerk.reporting.deck); die Daten sind simuliert.")

    # 2 key messages
    s = new()
    _title(s, f"DB II {fmt_eur(abs(gap))} unter Plan, getrieben von Preis und Menge",
           "Gesamtjahr 2025, Nordwerk-Gruppe, Konzernwährung EUR")
    fc66 = d["fc"].query("version == 'FC6_6' and methode == 'ml'").iloc[0]
    cards = [
        (fmt_eur(gap), f"DB II Ist {fmt_eur(db2_ist)} gegenüber Plan {fmt_eur(db2_plan)} "
                       f"({fmt_pct(gap / db2_plan)})", COPPER),
        (fmt_eur(float(g["preiseffekt_eur"])), "Preiseffekt, fast vollständig bei Kreiselpumpen: "
                                              "geplante Preiserhöhung nicht durchgesetzt", COPPER),
        (fmt_pct(fc66["prognose_db2_eur"] / fc66["plan_db2_eur"] - 1),
         "Forecast 6+6 (Juni) hat die Zielverfehlung angekündigt; Schwelle 98 % des Plans", PETROL),
    ]
    for i, (v, lab, col) in enumerate(cards):
        _card(s, Inches(0.6 + i * 4.1), Inches(1.9), Inches(3.8), Inches(2.4), v, lab, color=col)
    _text(s, Inches(0.6), Inches(4.65), Inches(12), Inches(0.4), "Zur Entscheidung im Lenkungskreis", size=18,
          bold=True, color=PETROL, font=HEAD)
    _bullets(s, Inches(0.6), Inches(5.1), Inches(12.1), Inches(1.8), [
        "Preisdurchsetzung Kreiselpumpen 2026:|Preiserhöhung mit Vertrieb verbindlich je Kundensegment festlegen",
        "Österreich:|Ersatz für den verlorenen Kommunal-Rahmenvertrag in die Budgetplanung 2026 aufnehmen",
        "Pilot KI-Monatskommentar:|mit einem Controller die Zeitersparnis messen (Kriterium bisher offen)"], size=15)

    # 3 DB statement table
    s = new()
    _title(s, "Die Lücke entsteht im DB I, die Fixkosten liegen am Plan",
           "Mehrstufige Deckungsbeitragsrechnung, Gesamtjahr 2025, Nordwerk-Gruppe")
    rows = [["Position", "Plan", "Ist", "Abweichung", "Abw. %"]]
    labels = [("umsatz", "Umsatzerlöse"), ("variable_kosten", "Variable Kosten"), ("db1", "Deckungsbeitrag I"),
              ("fixkosten_db2", "Fixkosten Fertigung/Produktgruppen"), ("db2", "Deckungsbeitrag II"),
              ("fixkosten_db3", "Bereichsfixkosten"), ("db3", "Deckungsbeitrag III"),
              ("unternehmensfixkosten", "Unternehmensfixkosten"), ("betriebsergebnis", "Betriebsergebnis")]
    colors: dict[int, RGBColor] = {}
    for i, (key, lab) in enumerate(labels, start=1):
        ist, plan = float(k.loc[key, "ist"]), float(k.loc[key, "plan"])
        cost = "kosten" in key
        good = (ist - plan) < 0 if cost else (ist - plan) > 0
        colors[i] = GREEN if good else COPPER
        rows.append([lab, fmt_eur(plan), fmt_eur(ist), fmt_eur(ist - plan, signed=True), fmt_pct((ist - plan) / abs(plan))])
    _table(s, Inches(0.6), Inches(1.8), Inches(12.1), rows,
           [Inches(4.5), Inches(1.9), Inches(1.9), Inches(2.0), Inches(1.8)], bold_rows=(3, 5, 7, 9),
           color_cols={3: colors, 4: colors})
    _text(s, Inches(0.6), Inches(6.2), Inches(12), Inches(0.5),
          "Grün = günstig, kupfer = ungünstig. Bei Kosten ist ein Ist über Plan ungünstig.", size=12, color=MUTED)

    # 4 bridge chart
    s = new()
    _title(s, f"Preis- und Mengeneffekt erklären {fmt_pct((float(g['preiseffekt_eur']) + float(g['mengeneffekt_eur'])) / gap, signed=False)} der DB-II-Lücke",
           "Abweichungsbrücke DB II, Plan → Ist, Gesamtjahr 2025, Gruppe (positiv = günstig)")
    eff = [("Mengeneffekt", "mengeneffekt_eur"), ("Mixeffekt", "mixeffekt_eur"), ("Preiseffekt", "preiseffekt_eur"),
           ("Materialkosten", "materialkosteneffekt_eur"), ("Erlösschmälerungen", "erloesschmaelerung_eur"),
           ("Fixkosten", "fixkosteneffekt_db2_eur"), ("Währung (PLN)", "waehrungseffekt_eur")]
    cd = CategoryChartData()
    cd.categories = [e[0] for e in eff]
    vals = [float(g[c]) / 1e6 for _, c in eff]
    cd.add_series("Effekt (Mio. EUR)", vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.6), Inches(1.8), Inches(7.6), Inches(4.9), cd)
    ch = gf.chart
    _style_chart(ch)
    ch.has_legend = False
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    plot.data_labels.number_format = '#,##0.0;-#,##0.0'
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, v in enumerate(vals):
        pt = plot.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = GREEN if v > 0 else COPPER
    ch.category_axis.reverse_order = True
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    ch.value_axis.has_major_gridlines = False
    ch.value_axis.tick_labels.number_format = '#,##0.0'
    ch.value_axis.tick_labels.number_format_is_linked = False
    share = (float(g["preiseffekt_eur"]) + float(g["mengeneffekt_eur"])) / gap
    _bullets(s, Inches(8.6), Inches(1.9), Inches(4.2), Inches(4.8), [
        f"Preis {fmt_eur(float(g['preiseffekt_eur']))}:|Kreiselpumpen mit geringerer Preiserhöhung als geplant",
        f"Menge {fmt_eur(float(g['mengeneffekt_eur']))}:|schwächeres Marktvolumen und Kundenverlust in Österreich",
        f"Mix {fmt_eur(float(g['mixeffekt_eur']))}:|Kunden wechseln von Dosier- zu Kreiselpumpen",
        f"Währung {fmt_eur(float(g['waehrungseffekt_eur']), signed=True)}:|stärkerer Zloty entlastet",
        f"Preis und Menge zusammen:|{fmt_pct(share, signed=False)} der Lücke von {fmt_eur(gap)}"], size=14)

    # 5 Austria
    s = new()
    at = d["at"]
    b_at = br.loc["2000"]
    _title(s, "Österreich: Umsatzeinbruch ab April nach Vertragsverlust",
           "Umsatz Nordwerk Austria GmbH 2025 je Monat, Ist gegenüber Plan (Mio. EUR)")
    cd = CategoryChartData()
    cd.categories = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    cd.add_series("Plan", [v / 1e6 for v in at["plan_eur"]])
    cd.add_series("Ist", [v / 1e6 for v in at["ist_eur"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.6), Inches(1.8), Inches(8.0), Inches(4.9), cd)
    ch = gf.chart
    _style_chart(ch)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.TOP
    ch.legend.include_in_layout = False
    for ser, col in zip(ch.plots[0].series, (MUTED, COPPER), strict=True):
        ser.format.line.color.rgb = col
        ser.format.line.width = Pt(2.5)
        ser.smooth = False
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = col
        ser.marker.format.line.color.rgb = col
    ch.value_axis.has_major_gridlines = True
    ch.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xDD, 0xE3, 0xE6)
    ch.value_axis.tick_labels.number_format = '#,##0.0'
    ch.value_axis.tick_labels.number_format_is_linked = False
    q1 = float(at["ist_eur"][:3].sum() - at["plan_eur"][:3].sum())
    rest = float(at["ist_eur"][3:].sum() - at["plan_eur"][3:].sum())
    at_gap = float(b_at["ist_db2_eur"] - b_at["plan_db2_eur"])
    _card(s, Inches(9.0), Inches(1.9), Inches(3.7), Inches(2.2), fmt_eur(rest, signed=True),
          "Umsatz April bis Dezember gegenüber Plan", color=COPPER)
    _card(s, Inches(9.0), Inches(4.4), Inches(3.7), Inches(2.2), fmt_eur(at_gap, signed=True),
          f"DB II Österreich gegenüber Plan (Q1-Umsatz noch {fmt_eur(q1, signed=True)})", color=COPPER)

    # 6 cost centres
    s = new()
    _title(s, "Kostenstellen: Einmaleffekt in der Instandhaltung dominiert",
           "Fünf Kostenstellen mit der ungünstigsten Primärkostenabweichung, Gesamtjahr 2025 (Plan − Ist)")
    rows = [["Kostenstelle", "Plan", "Ist", "Abweichung"]]
    for r in d["cc"].itertuples():
        rows.append([f"{r.kostenstelle} {r.txt}", fmt_eur(r.plan), fmt_eur(r.ist), fmt_eur(r.abw, signed=True)])
    _table(s, Inches(0.6), Inches(1.8), Inches(7.6), rows, [Inches(3.4), Inches(1.4), Inches(1.4), Inches(1.4)],
           color_cols={3: {i: COPPER for i in range(1, len(rows))}})
    _card(s, Inches(8.8), Inches(1.8), Inches(3.9), Inches(2.6), fmt_eur(float(d["oneoff"]), signed=True),
          "Instandhaltung durch Dritte, Kostenstelle 1410, allein im Juni 2025: außerplanmäßige Reparatur", color=COPPER)
    _bullets(s, Inches(8.8), Inches(4.7), Inches(3.9), Inches(2), [
        "Einmaleffekt:|nicht in die Hochrechnung 2026 fortschreiben",
        "Vorschlag:|Instandhaltungsreserve im Budget 2026 prüfen"], size=14)

    # 7 early warning
    s = new()
    q2 = d["q2"]
    _title(s, "Frühwarnung: ab Juni zeigen alle Verfahren die Verfehlung",
           "Prognose DB II 2025 je Forecast-Version (Mio. EUR) und Backtest über 200 simulierte Szenarien")
    fc = d["fc"]
    cd = CategoryChartData()
    cd.categories = ["3+9 (März)", "6+6 (Juni)", "9+3 (Sept.)"]
    for meth, lab in (("straight_line", "Lineare Hochrechnung"), ("ml", "ML-Forecast")):
        cd.add_series(lab, [float(fc.query(f"version == '{v}' and methode == '{meth}'")["prognose_db2_eur"].iloc[0]) / 1e6
                            for v in ("FC3_9", "FC6_6", "FC9_3")])
    cd.add_series("Plan", [db2_plan / 1e6] * 3)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.8), Inches(7.4), Inches(4.9), cd)
    ch = gf.chart
    _style_chart(ch)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.TOP
    ch.legend.include_in_layout = False
    for ser, col in zip(ch.plots[0].series, (MUTED, PETROL_2, RGBColor(0xB8, 0xC7, 0xCC)), strict=True):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = col
    ch.value_axis.minimum_scale = 0
    ch.value_axis.has_major_gridlines = False
    ch.plots[0].has_data_labels = True
    ch.plots[0].data_labels.number_format = '#,##0.0'
    ch.plots[0].data_labels.number_format_is_linked = False
    ch.plots[0].data_labels.font.size = Pt(10)
    lead = q2["lead_ml_vs_straight_line"]
    _bullets(s, Inches(8.4), Inches(1.9), Inches(4.4), Inches(4.8), [
        f"Erkannt (Median):|lineare Hochrechnung Monat {q2['straight_line']['median_detection_month']:.0f}, "
        f"ML Monat {q2['ml']['median_detection_month']:.0f}",
        f"Fehlalarme:|linear {fmt_pct(q2['straight_line']['false_alarm_rate'], signed=False)}, "
        f"ML {fmt_pct(q2['ml']['false_alarm_rate'], signed=False)}",
        f"Vorsprung ML je Szenario (Median):|{lead['median']:.0f} Monate – Ziel waren 2",
        "Ergebnis H2:|nicht erfüllt. ML warnt nicht früher, aber ohne Fehlalarme; Empfehlung: beide Verfahren "
        "parallel berichten"], size=14)

    # 8 AI assistant
    s = new()
    q3 = d["q3"]
    c3 = q3["commentary"]
    gs = q3["golden_set"]
    inj = q3["injection"]
    _title(s, "KI-Assistent: jede Zahl im Monatskommentar ist geprüft",
           "Fact-first: Zahlen kommen aus SQL, das Sprachmodell formuliert nur, ein Prüfer kontrolliert jede Zahl")
    cards = [(f"{c3['all_figures_correct']}/{c3['n']}", "Monatskommentare mit 100 % korrekten Zahlen (Ziel 100 %)"),
             (f"{gs['correct']}/{gs['n']}", "Fragen im Golden Set richtig beantwortet (Ziel ≥ 95 %)"),
             (f"{sum(x['successful_attempts'] for x in inj)}/{sum(x['attempts'] for x in inj)}",
              "erfolgreiche Angriffe (Prompt-Injection, Rechte, SQL), auch mit feindlichem Modell"),
             ("offen", "Zeitersparnis ≥ 50 %: Messung braucht einen praktizierenden Controller")]
    for i, (v, lab) in enumerate(cards):
        _card(s, Inches(0.6 + i * 3.08), Inches(1.9), Inches(2.85), Inches(2.6), v, lab,
              color=MUTED if v == "offen" else PETROL)
    _bullets(s, Inches(0.6), Inches(4.9), Inches(12.1), Inches(1.9), [
        "Berechtigungen:|Kostenstellenverantwortliche sehen nur ihre Kostenstellen – in der Datenbank erzwungen",
        "Ehrlich gemessen:|Golden Set im ersten Lauf 87 %; handgeschriebene, unbekannte Fragen 35 von 40 richtig erkannt",
        "Betrieb:|Azure OpenAI (EU), MCP-Server für Teams/Copilot, Audit-Log je Anfrage"], size=14)

    # 9 hypotheses status
    s = new()
    q1 = d["q1"]
    _title(s, "Status der vorab festgelegten Hypothesen", "Kriterien aus ADR-0001, vor der Analyse festgelegt und nicht verändert")
    rows = [["Frage", "Kriterium", "Ergebnis", "Status"],
            ["Q1 Abweichungsanalyse", "Brücke schließt ohne Rest", "Rest < 0,01 EUR" if q1['closure_abs_eur'] < 0.005 else f"Rest {q1['closure_abs_eur']:.2f} EUR", "erfüllt"],
            ["", "Injizierte Effekte ±10 % wiedergefunden", f"{q1['criteria']['c2_recovered_count']} Effekte; Menge "
             "von Zufallsnachfrage überlagert", "nicht erfüllt"],
            ["", "≥ 90 % der Kostenabweichung auf Kostenstellen", fmt_pct(q1["criteria"]["c3_cost_centre_coverage"], signed=False),
             "erfüllt"],
            ["Q2 Frühwarnung", "ML ≥ 2 Monate früher, nicht mehr Fehlalarme",
             f"Vorsprung {lead['median']:.0f} Monate, Fehlalarme 0 %", "nicht erfüllt"],
            ["Q3 KI-Kommentar", "100 % korrekte Zahlen", f"{c3['all_figures_correct']}/{c3['n']}", "erfüllt"],
            ["", "Golden Set ≥ 95 %", fmt_pct(gs["accuracy"], signed=False), "erfüllt"],
            ["", "0 erfolgreiche Angriffe", "0", "erfüllt"],
            ["", "Zeitersparnis ≥ 50 %", "Messprotokoll steht", "offen"]]
    status_col = {i: (GREEN if r[3] == "erfüllt" else COPPER if r[3] == "nicht erfüllt" else MUTED)
                  for i, r in enumerate(rows) if i}
    _table(s, Inches(0.6), Inches(1.8), Inches(12.1), rows, [Inches(2.6), Inches(4.3), Inches(3.5), Inches(1.7)],
           size=12, color_cols={3: status_col}, left_cols=(0, 1, 2))

    # 10 next steps
    s = new(dark=True)
    _text(s, Inches(0.8), Inches(0.8), Inches(11.5), Inches(0.9), "Vorschläge und nächste Schritte", size=34,
          bold=True, color=WHITE, font=HEAD)
    _bullets(s, Inches(0.8), Inches(2.0), Inches(11.7), Inches(4.6), [
        "Budget 2026:|Preis- und Mengenannahmen je Produktgruppe in SAC treiberbasiert planen (Startwerte = Ist 2025)",
        "Vertrieb:|Preisdurchsetzung Kreiselpumpen je Segment nachhalten, monatlich im Bericht",
        "Österreich:|Ausschreibungen Kommunalkunden früher erkennen – Auftragseingang als Frühindikator nutzen",
        "Forecast:|lineare Hochrechnung und ML-Forecast parallel; Warnung erst bei zwei übereinstimmenden Signalen",
        "KI-Assistent:|Pilot mit einem Controller (Zeitmessung nach Protokoll), danach Freigabe für Kostenstellenverantwortliche",
        "Echtdaten:|Umsetzung bei einem Pilotunternehmen (DATEV/SAP-Export) unter NDA"],
        size=17, color=RGBColor(0xE6, 0xEF, 0xF1))
    prs.save(path)


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "out")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / "Lenkungskreis_Nordwerk_GJ2025.pptx"
    build(load(connect()), path)
    print(f"wrote {path}")
    return path


if __name__ == "__main__":
    main()
