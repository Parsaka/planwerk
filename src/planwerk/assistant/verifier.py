"""Checks every number in a text against the fact sheet (ADR-0004, Q3 criterion 1).

A figure with a unit is accepted only if it is written exactly as the fact sheet renders one of
its facts ("6,4 Mio. EUR", "−11,6 %"). Numbers reach a text through placeholders that code fills
in, so any other notation ("6 Millionen Euro", "EUR 6 Mio.", "sechs Millionen") was typed by the
model. Comparing values with a rounding tolerance instead would let a coarsely rounded invention
pass whenever some fact happens to lie within half a unit of it.

Limit, by construction: a real figure under the wrong label ("Umsatz" next to the DB II value)
is a figure of the fact sheet and passes. Labels are fixed by the templates, not by this check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from planwerk.assistant.facts import FactSheet
from planwerk.assistant.formatting import MINUS, fmt, parse_numbers, spelled_numbers


@dataclass
class VerificationResult:
    ok: bool
    checked: int
    unverified: list[str] = field(default_factory=list)


def _canon(token: str) -> str:
    return re.sub(r"\s+", " ", token.replace("-", MINUS)).strip()


def rendered_facts(sheet: FactSheet) -> set[str]:
    """Every way the fact sheet itself writes one of its EUR or percent facts."""
    out = set()
    for f in sheet.facts.values():
        if f.unit in ("EUR", "PCT"):
            for signed in (False, True):
                out.add(_canon(fmt(f.value, f.unit, signed=signed)))
    return out


def verify(text: str, sheet: FactSheet) -> VerificationResult:
    tokens = parse_numbers(text)
    bad = []
    values = [(f.value, f.unit) for f in sheet.facts.values()]
    rendered = rendered_facts(sheet)
    for t in tokens:
        if t.unit == "NONE":
            raw = t.text.lstrip("+-−").strip()
            if raw in sheet.allowed_tokens:
                continue
            if raw.isdigit() and (2020 <= int(raw) <= 2030 or 1 <= int(raw) <= 31):
                continue  # years, days, months
            if any(u in ("DEC", "INT") and abs(abs(v) - abs(t.value)) <= t.tolerance for v, u in values):
                continue
            bad.append(t.text)
            continue
        if _canon(t.text) not in rendered:
            bad.append(t.text)
    bad += spelled_numbers(text)  # a figure in words cannot be traced to a fact
    return VerificationResult(ok=not bad, checked=len(tokens), unverified=bad)
