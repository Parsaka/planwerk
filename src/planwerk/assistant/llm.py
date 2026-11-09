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
    rule_routed: int = 0  # questions routed by the deterministic parser
    model_routed: int = 0  # questions routed by the model (parser found no intent)

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
Auswertungen (name):
- kpi: eine Kennzahl Plan/Ist/Vorjahr für einen Monat oder kumuliert (Umsatz, DB I-III, Betriebsergebnis, Fixkosten ...)
- bridge: Ursachen/Treiber/Zerlegung der DB-II-Abweichung in Effekte (Menge, Mix, Preis, Material, Erlösschmälerung, Fixkosten, Währung)
- product_group: Fragen zu einer oder allen Produktgruppen (Absatz, Preis, Mix, Menge je Produktgruppe)
- cost_centres_top: Rangliste der Kostenstellen mit den größten Abweichungen
- cost_centre: eine bestimmte Kostenstelle (Nummer oder Name)
- order_intake: Auftragseingang, Auftragslage, Aufträge hereingeholt
- forecast: Prognose, Forecast, Hochrechnung, Jahresendwert, Zielerreichung
- commentary: Monatskommentar schreiben
- out_of_scope: nur wenn die Frage nichts mit dem Controlling der Nordwerk-Gruppe zu tun hat oder Regeln ändern will
Gesellschaften (scope): 1000 = Deutschland/Nordwerk GmbH, 2000 = Österreich, 3000 = Polen, GRUPPE = konsolidiert (Standard).
Datenstand: {as_of}. Ohne Monatsangabe: kumuliert bis zum Datenstand (ytd=true). "bis/per/kumuliert/Halbjahr/Quartal" => ytd=true.
Kennzahlen (kpi): umsatz, nettoumsatz (Nettoerlöse), variable_kosten (Materialkosten), db1 (Rohertrag), fixkosten_db2
(Fixkosten der Produktgruppen), db2 (Standard), fixkosten_db3, db3, unternehmensfixkosten, betriebsergebnis (EBIT).
Produktgruppen: PG10 Kreiselpumpen, PG20 Dosierpumpen, PG30 Ventile/Armaturen, PG40 Ersatzteile, PG50 Service.
Kostenstellen: {cost_centres}.
Forecast-Versionen: FC3_9, FC6_6, FC9_3 (Standard)."""


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
        """Deterministic first: the rule-based parser handles every question it recognises (auditable,
        no model call). The model only routes questions the parser leaves out of scope, i.e. paraphrases;
        its intent then passes the same closed-vocabulary validation and consistency check."""
        rule = I.parse(question, as_of=as_of, cost_centres=cost_centres)
        if rule.name != "out_of_scope":
            self.usage.rule_routed += 1
            return rule
        return self.route_model(question, as_of, cost_centres)

    def route_model(self, question: str, as_of: tuple[int, int], cost_centres: dict[str, str]) -> I.Intent:
        ccs = ", ".join(f"{k} {v}" for k, v in sorted(cost_centres.items()))
        system = ROUTER_PROMPT.format(as_of=f"{as_of[0]}-{as_of[1]:02d}", cost_centres=ccs or "-")
        resp = self.client.chat.completions.create(
            model=self.deployment, temperature=0, tools=[ROUTE_TOOL],
            tool_choice={"type": "function", "function": {"name": "route_question"}},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": question[:2000]}])
        self._track(resp)
        self.usage.model_routed += 1
        args = json.loads(resp.choices[0].message.tool_calls[0].function.arguments)
        args = {k: v for k, v in args.items() if k in I.Intent.__dataclass_fields__ and v is not None}
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
