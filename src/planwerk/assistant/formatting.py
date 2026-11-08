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
_UNIT = r"\s?(?P<unit>Mio\.\s?EUR|Mrd\.\s?EUR|TEUR|EUR|%|Prozent)?"
TOKEN_RE = re.compile(_NUM + _UNIT)


def parse_numbers(text: str) -> list[NumberToken]:
    out = []
    for m in TOKEN_RE.finditer(text):
        # skip digits that are part of identifiers like PG10, 0L, Q4, FC3_9
        st = m.start("num") if m.group("sign") is None else m.start()
        if st > 0 and (text[st - 1].isalnum() or text[st - 1] in "_.,"):
            continue
        num = m.group("num")
        dec = len(num.split(",")[1]) if "," in num else 0
        v = float(num.replace(".", "").replace(",", "."))
        sign = m.group("sign")
        if sign in ("-", "−"):
            v = -v
        unit = (m.group("unit") or "").replace(" ", "")
        if unit in ("Mio.EUR",):
            scale, u = 1e6, "EUR"
        elif unit == "Mrd.EUR":
            scale, u = 1e9, "EUR"
        elif unit == "TEUR":
            scale, u = 1e3, "EUR"
        elif unit == "EUR":
            scale, u = 1.0, "EUR"
        elif unit in ("%", "Prozent"):
            scale, u = 0.01, "PCT"
        else:
            scale, u = 1.0, "NONE"
        out.append(NumberToken(m.group(0).strip(), v * scale, u, 0.5 * 10 ** (-dec) * scale + 1e-9, m.start()))
    return out
