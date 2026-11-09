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
    # model calls that failed after the client's retries (rate limit, timeout, outage) and were
    # answered without the model: "out of scope" for routing, the template draft for wording
    fallbacks: int = 0

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


# Deployment names of reasoning models. They reject ``temperature`` and ``max_tokens`` and take
# ``max_completion_tokens`` (which also has to cover the hidden reasoning tokens) instead.
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
REASONING_TOKEN_BUDGET = 1500
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


def _is_content_filter(err: Exception) -> bool:
    return getattr(err, "code", None) == "content_filter" or "content_filter" in str(err).lower() \
        or "content management policy" in str(err).lower()


class AzureOpenAIProvider:
    """Azure OpenAI deployment for routing and wording.

    Needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT, and either AZURE_OPENAI_API_KEY or an
    Entra ID identity (``az login``, managed identity, or OIDC federation in GitHub Actions).
    Optional: AZURE_OPENAI_API_VERSION (default ``2024-10-21``, the classic endpoint; ``v1`` uses
    the versionless ``/openai/v1/`` endpoint), AZURE_OPENAI_MODEL (model behind the
    deployment), AZURE_OPENAI_MODEL_FAMILY (``reasoning`` | ``classic``; default from the model or
    deployment name, corrected automatically if the deployment rejects the parameters) and
    AZURE_OPENAI_REASONING_EFFORT (default ``low``; empty = do not send it).

    Routing is deterministic first (:meth:`route`); the model routes only what the rule-based parser
    leaves out of scope (:meth:`route_model`). The provider never decides a figure. If the service is
    unavailable after the client's retries, such a question stays out of scope and wording falls
    back to the template draft; these calls are counted in ``usage.fallbacks`` so that an
    evaluation cannot mistake them for model output.
    """

    name = "azure_openai"
    max_retries = 6      # the SDK waits as long as the service asks (HTTP 429 Retry-After)
    timeout_s = 90.0
    reasoning = False    # set per instance from the model name, corrected from the service's error
    reasoning_effort: str | None = "low"

    def __init__(self, client=None, deployment: str | None = None) -> None:
        self.deployment = deployment or os.environ["AZURE_OPENAI_DEPLOYMENT"]
        family = os.environ.get("AZURE_OPENAI_MODEL_FAMILY")
        model = os.environ.get("AZURE_OPENAI_MODEL", self.deployment).lower()
        self.reasoning = (family == "reasoning") if family else model.startswith(REASONING_PREFIXES)
        self.reasoning_effort = os.environ.get("AZURE_OPENAI_REASONING_EFFORT", "low") or None
        self.client = client or self._make_client()
        self.usage = Usage()

    def _make_client(self):
        import openai

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        common = dict(max_retries=self.max_retries, timeout=self.timeout_s)
        key = os.environ.get("AZURE_OPENAI_API_KEY")
        if not key:  # keyless: Entra ID token (managed identity in Azure, OIDC federation in GitHub Actions)
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), os.environ.get("AZURE_OPENAI_TOKEN_SCOPE", TOKEN_SCOPE))
        if api_version == "v1":
            return openai.OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=key or token_provider, **common)
        if key:
            return openai.AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version=api_version, **common)
        return openai.AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token_provider,
                                  api_version=api_version, **common)

    def _params(self, max_out: int, temperature: float) -> dict:
        if self.reasoning:
            p = dict(max_completion_tokens=max_out + REASONING_TOKEN_BUDGET)
            if self.reasoning_effort:
                p["reasoning_effort"] = self.reasoning_effort
            return p
        return dict(max_tokens=max_out, temperature=temperature)

    def _chat(self, messages: list[dict], max_out: int, temperature: float, **kw):
        """One completion. If the deployment rejects the parameter set of the assumed model family
        (HTTP 400 naming the parameter), switch family once and repeat."""
        import openai

        for _ in range(3):
            try:
                resp = self.client.chat.completions.create(model=self.deployment, messages=messages,
                                                           **self._params(max_out, temperature), **kw)
                break
            except openai.BadRequestError as e:
                msg = str(e).lower()
                if self.reasoning and self.reasoning_effort and "reasoning_effort" in msg:
                    self.reasoning_effort = None
                elif not self.reasoning and ("max_tokens" in msg or "temperature" in msg):
                    self.reasoning = True
                elif self.reasoning and "max_completion_tokens" in msg:
                    self.reasoning = False
                else:
                    raise
        else:
            raise RuntimeError("deployment rejected every parameter set")
        u = getattr(resp, "usage", None)
        if u is not None:
            self.usage.prompt_tokens += u.prompt_tokens
            self.usage.completion_tokens += u.completion_tokens
        self.usage.calls += 1
        return resp

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
        import openai

        ccs = ", ".join(f"{k} {v}" for k, v in sorted(cost_centres.items()))
        system = ROUTER_PROMPT.format(as_of=f"{as_of[0]}-{as_of[1]:02d}", cost_centres=ccs or "-")
        try:
            resp = self._chat([{"role": "system", "content": system}, {"role": "user", "content": question[:2000]}],
                              max_out=300, temperature=0, tools=[ROUTE_TOOL],
                              tool_choice={"type": "function", "function": {"name": "route_question"}})
        except openai.BadRequestError as e:
            if _is_content_filter(e):  # the service refused the prompt: nothing to answer
                return I.Intent(name="out_of_scope")
            raise
        except openai.APIError:  # rate limit, timeout or outage after all retries; the parser found nothing
            self.usage.fallbacks += 1
            return I.Intent(name="out_of_scope")
        self.usage.model_routed += 1
        # anything malformed below raises and the graph answers "out of scope" (never reaches SQL)
        args = json.loads(resp.choices[0].message.tool_calls[0].function.arguments)
        args = {k: v for k, v in args.items() if k in I.Intent.__dataclass_fields__ and v is not None}
        args.setdefault("month_given", True)
        return I.Intent(**args)

    def rewrite(self, system: str, user: str, draft: str) -> str:
        import openai

        try:
            resp = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                              max_out=600, temperature=0.2)
        except openai.APIError:  # the verified template draft is always a valid answer
            self.usage.fallbacks += 1
            return draft
        return (resp.choices[0].message.content or "").strip() or draft


def get_provider(name: str | None = None):
    name = name or os.environ.get("PLANWERK_LLM", "auto")
    if name == "offline":
        return OfflineProvider()
    if name in ("azure", "azure_openai") or (name == "auto" and os.environ.get("AZURE_OPENAI_ENDPOINT")):
        return AzureOpenAIProvider()
    return OfflineProvider()
