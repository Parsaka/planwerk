"""Fact sheet: the only source of numbers for any text the assistant writes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from planwerk.assistant.formatting import fmt

PLACEHOLDER = re.compile(r"\{\{\s*f:([a-z0-9_]+)(\|signed)?\s*\}\}")


@dataclass
class Fact:
    id: str
    label: str
    value: float
    unit: str  # EUR | PCT | INT | DEC
    source: str = ""


@dataclass
class FactSheet:
    facts: dict[str, Fact] = field(default_factory=dict)
    allowed_tokens: set[str] = field(default_factory=set)  # ids/years that may appear without unit

    def add(self, id: str, label: str, value: float, unit: str = "EUR", source: str = "") -> Fact:
        if value is None:
            value = 0.0
        f = Fact(id, label, float(value), unit, source)
        self.facts[id] = f
        return f

    def render(self, template: str) -> str:
        def rep(m: re.Match) -> str:
            fid = m.group(1)
            if fid not in self.facts:
                raise KeyError(f"unknown fact id {fid}")
            f = self.facts[fid]
            return fmt(f.value, f.unit, signed=bool(m.group(2)))
        return PLACEHOLDER.sub(rep, template)

    def for_prompt(self) -> str:
        return "\n".join(f"- {f.id}: {f.label} = {fmt(f.value, f.unit)}" for f in self.facts.values())

    def to_list(self) -> list[dict]:
        return [asdict(f) for f in self.facts.values()]
