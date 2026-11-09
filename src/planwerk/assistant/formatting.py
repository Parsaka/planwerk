"""German number formatting for controlling texts and the inverse parser used by the verifier."""

from __future__ import annotations

import re
from dataclasses import dataclass

MINUS = "−"  # typographic minus; the parser also accepts '-'


def _de(x: float, decimals: int) -> str:
    s = f"{abs(x):,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return (MINUS if x < 0 and float(f"{abs(x):.{decimals}f}") != 0 else "") + s


def fmt_eur(v: float, signed: bool = False) -> str:
    """12,3 Mio. EUR | 456 TEUR | 789 EUR."""
    a = abs(v)
    if a >= 999_950:  # thresholds on the rounded value: 999.960 EUR -> 1,0 Mio. EUR, not 1.000 TEUR
        out = _de(v / 1e6, 1) + " Mio. EUR"
    elif a >= 999.5:
        out = _de(v / 1e3, 0) + " TEUR"
    else:
        out = _de(v, 0) + " EUR"
    if signed and v > 0 and not out.startswith("0"):
        out = "+" + out
    return out


def fmt_pct(v: float, signed: bool = True) -> str:
    """v is a ratio (0.032 -> '+3,2 %')."""
    out = _de(v * 100, 1) + " %"
    if signed and v > 0 and float(f"{v * 100:.1f}") != 0:
        out = "+" + out
    return out


def fmt(value: float, unit: str, signed: bool = False) -> str:
    if unit == "EUR":
        return fmt_eur(value, signed)
    if unit == "PCT":
        return fmt_pct(value, signed)
    if unit == "INT":
        return _de(value, 0)
    if unit == "DEC":
        return _de(value, 2)
    raise ValueError(unit)


@dataclass(frozen=True)
class NumberToken:
    text: str
    value: float      # in base unit: EUR, or ratio for %, or plain number
    unit: str         # EUR | PCT | NONE
    tolerance: float  # half of the last displayed digit, in base unit
    start: int


_NUM = r"(?:(?P<sign>[+\-−])\s?)?(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
_END = r"(?![A-Za-zÄÖÜäöüß])"  # the unit word ends here ("Mio" but not "Minuten", "Euro" but not "Europa")
# Every way a model may write a magnitude or a currency, not only the house style "Mio. EUR":
# "7 Millionen Euro", "7 Mio €", "950 T€", "30 Tsd. EUR", "28 k€", "9 Mrd." all carry a figure.
_MAG = (r"(?P<mag>Mrd\.|Mrd" + _END + r"|Milliarden?" + _END + r"|Mio\.|Mio" + _END + r"|Million(?:en)?" + _END
        + r"|Tsd\.|Tsd" + _END + r"|Tausend" + _END + r"|[Tk](?=\s?(?:EUR|€)))")
_CUR = r"(?P<cur>EUR" + _END + r"|Euro" + _END + r"|€)"
_PCT = r"(?P<pct>%|Prozentpunkte?n?" + _END + r"|Prozent" + _END + r"|v\.\s?H\.)"
_PRE = r"(?:(?P<pre>EUR|€)\s?)?"  # "EUR 12 Mio."
TOKEN_RE = re.compile(_PRE + _NUM + r"(?:\s?(?:" + _MAG + r"(?:\s?" + _CUR + r")?|" + _CUR.replace("<cur>", "<cur2>")
                      + r"|" + _PCT + r"))?")
# Figures written as words next to a unit ("zwölf Millionen Euro", "drei Prozent") cannot be checked
# against the fact sheet, so the verifier rejects them. The writer is told to use placeholders only.
_NUMBER_WORD = (r"(?:ein(?:e[rmns]?)?|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwoelf"
                r"|[a-zäöüß]*zehn|[a-zäöüß]*zig|[a-zäöüß]*ßig|[a-zäöüß]*hundert[a-zäöüß]*|[a-zäöüß]*tausend[a-zäöüß]*"
                r"|halbe?[rsn]?|anderthalb|eineinhalb|dutzend|mehrere|einige|etliche)")
_UNIT_WORD = (r"(?:Mrd\.?|Milliarden?|Mio\.?|Million(?:en)?|Tsd\.?|Tausend|TEUR|T€|EUR|Euro|€|%|Prozentpunkte?n?"
              r"|Prozent)" + _END)
SPELLED_RE = re.compile(r"(?<![A-Za-zÄÖÜäöüß])" + _NUMBER_WORD + r"\s(?:(?:komma|und)\s\w+\s)?" + _UNIT_WORD,
                        re.IGNORECASE)


def spelled_numbers(text: str) -> list[str]:
    """Figures written in words directly before a magnitude, currency or percent word."""
    return [m.group(0) for m in SPELLED_RE.finditer(text)]


def _scale(mag: str | None) -> float:
    if not mag:
        return 1.0
    m = mag.lower()
    if m.startswith(("mrd", "milliard")):
        return 1e9
    if m.startswith(("mio", "million")):
        return 1e6
    return 1e3  # Tsd., Tausend, T, k


def parse_numbers(text: str) -> list[NumberToken]:
    out = []
    for m in TOKEN_RE.finditer(text):
        # skip digits that are part of identifiers like PG10, 0L, Q4, FC3_9
        st = m.start("num") if m.group("sign") is None else m.start("sign")
        if st > 0 and (text[st - 1].isalnum() or text[st - 1] in "_.,") and not m.group("pre"):
            continue
        num = m.group("num")
        dec = len(num.split(",")[1]) if "," in num else 0
        v = float(num.replace(".", "").replace(",", "."))
        sign = m.group("sign")
        if sign in ("-", "−"):
            v = -v
        if m.group("pct"):
            scale, u = 0.01, "PCT"
        elif m.group("mag") or m.group("cur") or m.group("cur2") or m.group("pre"):
            scale, u = _scale(m.group("mag")), "EUR"
        else:
            scale, u = 1.0, "NONE"
        out.append(NumberToken(m.group(0).strip(), v * scale, u, 0.5 * 10 ** (-dec) * scale + 1e-9, m.start()))
    return out
