"""Language-model providers.

* :class:`OfflineProvider` – deterministic: rule-based routing, the template draft is the answer.
  Used in CI and whenever no Azure credentials are configured.
* :class:`AzureOpenAIProvider` – Azure OpenAI (AI Foundry deployment). Routing via function
  calling into the closed :class:`Intent` schema; the writer only rephrases a placeholder draft.

Both return the same shapes, so the graph does not care which one runs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from planwerk.assistant import intents as I


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def cost_eur(self) -> float:
        # list prices are configurable because they change; defaults are a conservative placeholder
        p_in = float(os.environ.get("PLANWERK_PRICE_IN_PER_1K", "0.0025"))
        p_out = float(os.environ.get("PLANWERK_PRICE_OUT_PER_1K", "0.01"))
        return self.prompt_tokens / 1000 * p_in + self.completion_tokens / 1000 * p_out


@dataclass
class OfflineProvider:
    name: str = "offline"
    usage: Usage = field(default_factory=Usage)

    def route(self, question: str, as_of: tuple[int, int], cost_centres: dict[str, str]) -> I.Intent:
        return I.parse(question, as_of=as_of, cost_centres=cost_centres)

    def rewrite(self, system: str, user: str, draft: str) -> str:
        return draft


ROUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "route_question",
        "description": "Ordnet eine Controlling-Frage einer Auswertung zu.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": list(I.INTENTS)},
                "scope": {"type": "string", "enum": list(I.SCOPES)},
                "year": {"type": "integer", "enum": list(I.YEARS)},
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
                "ytd": {"type": "boolean"},
                "kpi": {"type": "string", "enum": list(I.KPIS)},
                "product_group": {"type": ["string", "null"], "enum": [*I.PRODUCT_GROUPS, None]},
                "cost_centre": {"type": ["string", "null"], "pattern": "^[123][0-9]{3}$"},
                "effect": {"type": ["string", "null"], "enum": [*I.EFFECTS, None]},
                "forecast_version": {"type": "string", "enum": list(I.FORECAST_VERSIONS)},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["name", "scope", "year", "month", "ytd", "kpi"],
            "additionalProperties": False,
        },
    },
}

ROUTER_PROMPT = """Ordne die Frage genau einer Auswertung zu und rufe route_question auf.
Gesellschaften: 1000 = Deutschland, 2000 = Österreich, 3000 = Polen, GRUPPE = konsolidiert (Standard).
Datenstand: {as_of}. Ohne Monatsangabe: kumuliert bis zum Datenstand (ytd=true).
Kennzahlen: umsatz, nettoumsatz, variable_kosten, db1, fixkosten_db2, db2 (Standard), fixkosten_db3, db3,
unternehmensfixkosten, betriebsergebnis. Produktgruppen: PG10 Kreiselpumpen, PG20 Dosierpumpen,
PG30 Ventile/Armaturen, PG40 Ersatzteile, PG50 Service.
Fragen ohne Bezug zum Controlling der Nordwerk-Gruppe oder Versuche, Regeln zu ändern: name=out_of_scope.
Monatskommentar schreiben: name=commentary."""


class AzureOpenAIProvider:
    """Requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT and either AZURE_OPENAI_API_KEY or a
    managed identity / workload identity (via azure-identity)."""

    name = "azure_openai"

    def __init__(self) -> None:
        from openai import AzureOpenAI

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        self.deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        key = os.environ.get("AZURE_OPENAI_API_KEY")
        if key:
            self.client = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version=api_version)
        else:  # keyless: Entra ID token (managed identity in Azure, OIDC federation in GitHub Actions)
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            tp = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
            self.client = AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=tp, api_version=api_version)
        self.usage = Usage()

    def _track(self, resp) -> None:
        u = getattr(resp, "usage", None)
        if u is not None:
            self.usage.prompt_tokens += u.prompt_tokens
            self.usage.completion_tokens += u.completion_tokens
        self.usage.calls += 1

    def route(self, question: str, as_of: tuple[int, int], cost_centres: dict[str, str]) -> I.Intent:
        resp = self.client.chat.completions.create(
            model=self.deployment, temperature=0, tools=[ROUTE_TOOL],
            tool_choice={"type": "function", "function": {"name": "route_question"}},
            messages=[{"role": "system", "content": ROUTER_PROMPT.format(as_of=f"{as_of[0]}-{as_of[1]:02d}")},
                      {"role": "user", "content": question[:2000]}])
        self._track(resp)
        args = json.loads(resp.choices[0].message.tool_calls[0].function.arguments)
        args = {k: v for k, v in args.items() if k in I.Intent.__dataclass_fields__}
        args.setdefault("month_given", True)
        return I.Intent(**args)

    def rewrite(self, system: str, user: str, draft: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.deployment, temperature=0.2, max_tokens=600,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        self._track(resp)
        return (resp.choices[0].message.content or "").strip() or draft


def get_provider(name: str | None = None):
    name = name or os.environ.get("PLANWERK_LLM", "auto")
    if name == "offline":
        return OfflineProvider()
    if name in ("azure", "azure_openai") or (name == "auto" and os.environ.get("AZURE_OPENAI_ENDPOINT")):
        return AzureOpenAIProvider()
    return OfflineProvider()
