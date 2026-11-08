"""Checks every number in a text against the fact sheet (ADR-0004, Q3 criterion 1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from planwerk.assistant.facts import FactSheet
from planwerk.assistant.formatting import parse_numbers


@dataclass
class VerificationResult:
    ok: bool
    checked: int
    unverified: list[str] = field(default_factory=list)


def verify(text: str, sheet: FactSheet) -> VerificationResult:
    tokens = parse_numbers(text)
    bad = []
    values = [(f.value, f.unit) for f in sheet.facts.values()]
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
        unit = "EUR" if t.unit == "EUR" else "PCT"
        hit = any(u == unit and (abs(v - t.value) <= t.tolerance or abs(abs(v) - abs(t.value)) <= t.tolerance)
                  for v, u in values if u in ("EUR", "PCT"))
        if not hit:
            bad.append(t.text)
    return VerificationResult(ok=not bad, checked=len(tokens), unverified=bad)
