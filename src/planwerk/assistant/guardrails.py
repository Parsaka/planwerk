"""Input and output guardrails (first line of defence; the hard guarantees are structural:
closed intents, SQL guard, read-only connection, row-level security in the views, verifier).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_QUESTION_CHARS = 1000

_RULES: list[tuple[str, str]] = [
    ("instruction_override", r"(ignorier\w*|vergiss|missacht\w*|ueberschreib\w*|ignore|disregard|forget)\b.{0,40}"
                             r"(anweisung\w*|regel\w*|instruction\w*|vorgaben|prompt|richtlinie\w*|rules)"),
    ("instruction_override", r"\b(du bist (jetzt|ab sofort|nun)|you are now|act as|tu so als|spiel\w* die rolle"
                             r"|developer mode|entwicklermodus|jailbreak|dan mode)\b"),
    ("instruction_override", r"(#+ ?system\b|\[system\]|<\|?system\|?>|antworte (ab jetzt|ab sofort|nur noch|immer)"
                             r"|from now on|ab jetzt gilt)"),
    ("prompt_leak", r"\b(system ?prompt|systemnachricht|deine (anweisungen|instruktionen|regeln)|initial prompt"
                    r"|verborgene anweisung\w*|hidden instruction\w*)\b"),
    ("sql_injection", r"(\bdrop\s+(table|view|schema)\b|\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b"
                      r"|\btruncate\b|\balter\s+table\b|\bgrant\b|\bcreate\s+(table|user|role)\b|;\s*--|\bunion\s+select\b"
                      r"|\bselect\s+\*?\s*from\b|\battach\b|\bcopy\s+\w+\s+to\b|read_parquet|information_schema)"),
    ("privilege_escalation", r"\b(ich bin (der |die )?(controller|admin\w*|geschaeftsfuehr\w*|cfo)"
                             r"|als (admin|administrator|controller|geschaeftsfuehrung)|gib mir (vollen |alle )?"
                             r"(zugriff|rechte|berechtigung\w*)|set variable|planwerk_user|rolle wechseln"
                             r"|row access|rls (aus|deaktivier\w*))\b"),
    ("credential_request", r"\b(passwort\w*|password|api[- ]?key|zugangsdaten|token|secret|credential\w*"
                           r"|verbindungszeichenfolge|connection string)\b"),
    ("personal_data", r"\b(was verdient|gehalt (von|des|der) (herrn?|frau|kollege\w*|mitarbeiter\w*)|einzelne[nr]? "
                      r"mitarbeiter\w*|privatadresse|iban|geburtsdatum|krankheitstage|personalakte)\b"),
    ("fabrication", r"\b(erfinde|denk dir \w* aus|schaetz\w* (einfach|frei)|ausgedacht\w*|fiktive zahlen"
                    r"|make up|beschoenig\w*|frisier\w*)\b"),
]


@dataclass
class GuardResult:
    blocked: bool
    category: str | None = None
    message: str = ""


MESSAGES = {
    "too_long": "Die Frage ist zu lang. Bitte stellen Sie eine konkrete Controlling-Frage.",
    "instruction_override": "Diese Anweisung kann ich nicht befolgen. Ich beantworte Controlling-Fragen auf "
                            "Basis der freigegebenen Auswertungen.",
    "prompt_leak": "Interne Konfiguration gebe ich nicht heraus.",
    "sql_injection": "Ich führe keine eigenen SQL-Befehle aus. Bitte stellen Sie Ihre Frage in Worten.",
    "privilege_escalation": "Berechtigungen kann ich nicht ändern. Ihre Rechte ergeben sich aus dem "
                            "Berechtigungskonzept; wenden Sie sich an das Controlling.",
    "credential_request": "Zugangsdaten oder Schlüssel gebe ich nicht heraus.",
    "personal_data": "Personenbezogene Daten einzelner Beschäftigter sind nicht Teil der Auswertungen.",
    "fabrication": "Ich nenne nur Zahlen, die aus den Daten berechnet sind, und keine geschätzten oder "
                   "veränderten Werte.",
}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = re.sub(r"[​-‏⁠﻿]", "", t)  # zero-width characters used to hide payloads
    return re.sub(r"\s+", " ", t)


def check_input(question: str) -> GuardResult:
    if len(question) > MAX_QUESTION_CHARS:
        return GuardResult(True, "too_long", MESSAGES["too_long"])
    t = _norm(question)
    for cat, pat in _RULES:
        if re.search(pat, t):
            return GuardResult(True, cat, MESSAGES[cat])
    return GuardResult(False)


_LEAK_MARKERS = ("Regeln, ohne Ausnahme", "route_question", "Faktenblatt:", "{{f:")


def check_output(text: str) -> GuardResult:
    """Block answers that echo the system prompt or contain unrendered placeholders."""
    for m in _LEAK_MARKERS:
        if m in text:
            return GuardResult(True, "output_leak", "Die Antwort konnte nicht sicher erstellt werden.")
    return GuardResult(False)
