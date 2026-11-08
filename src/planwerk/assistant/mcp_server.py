"""MCP server: exposes the controlling assistant as read-only tools for MCP clients
(Claude Desktop, Copilot Studio via MCP connector, VS Code, ...).

Run:  python -m planwerk.assistant.mcp_server            (stdio)
      python -m planwerk.assistant.mcp_server --http     (streamable HTTP, behind an auth proxy)

The user identity comes from the environment (PLANWERK_MCP_USER) or, over HTTP, from the
authenticated principal set by the gateway; a tool argument can never raise privileges.
"""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from planwerk.assistant.graph import Assistant
from planwerk.assistant.intents import MONTH_TEXT, SCOPES

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    name="planwerk-controlling",
    title="Planwerk Controlling-Assistent",
    instructions=("Beantwortet Controlling-Fragen zur (simulierten) Nordwerk-Gruppe: Plan/Ist, DB I-III, "
                  "Abweichungsbrücke, Produktgruppen, Kostenstellen, Auftragseingang, Forecast, Monatskommentar. "
                  "Alle Zahlen stammen aus SQL auf freigegebenen Sichten und sind geprüft. Zahlen nicht verändern."),
    version="0.1.0",
)
_assistant: Assistant | None = None


def _get() -> Assistant:
    global _assistant
    if _assistant is None:
        _assistant = Assistant()
    return _assistant


def _user() -> str:
    return os.environ.get("PLANWERK_MCP_USER", "controller")


def _public(r: dict) -> dict:
    keys = ("answer", "status", "verified", "facts", "intent")
    return {k: r.get(k) for k in keys if k in r}


@server.tool(name="frage_controlling", annotations=READ_ONLY,
             description="Stellt eine Controlling-Frage auf Deutsch, z. B. 'Warum liegt der DB II in Österreich "
                         "unter Plan?'. Antwort mit geprüften Zahlen und Faktenliste.")
def frage_controlling(frage: str) -> dict:
    return _public(_get().ask(frage, user=_user()))


@server.tool(name="monatskommentar", annotations=READ_ONLY,
             description="Schreibt den Controlling-Monatskommentar für eine Gesellschaft (1000 DE, 2000 AT, "
                         "3000 PL, GRUPPE) und einen Monat (jahr, monat).")
def monatskommentar(bereich: str, jahr: int, monat: int) -> dict:
    if bereich not in SCOPES or monat not in MONTH_TEXT or jahr not in (2023, 2024, 2025):
        return {"status": "invalid", "answer": "Ungültige Auswahl (bereich 1000/2000/3000/GRUPPE, 2023-2025)."}
    r = _get().commentary(bereich, jahr, monat, user=_user())
    return _public(r)


@server.tool(name="verfuegbare_auswertungen", annotations=READ_ONLY,
             description="Listet, welche Auswertungen der Assistent beantworten kann.")
def verfuegbare_auswertungen() -> dict:
    return {"auswertungen": [
        "Kennzahl Plan/Ist/Vorjahr (Umsatz, DB I, DB II, DB III, Betriebsergebnis, Kostenblöcke), Monat oder kumuliert",
        "Abweichungsbrücke DB II (Menge, Mix, Preis, Materialkosten, Erlösschmälerungen, Fixkosten, Währung)",
        "Produktgruppen mit Preis-, Mengen-, Mix- und Materialkosteneffekt",
        "Kostenstellen mit der größten Abweichung, Kostenstelle im Detail (Zeilenberechtigung)",
        "Auftragseingang und Book-to-Bill", "Rolling Forecast 3+9 / 6+6 / 9+3 und Zielerreichung",
        "Monatskommentar je Gesellschaft"], "datenstand": "2025-12", "daten": "simuliert"}


def main() -> None:
    if "--http" in sys.argv:
        server.run("streamable-http")
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
