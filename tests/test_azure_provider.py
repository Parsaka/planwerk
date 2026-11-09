"""Azure OpenAI provider against a fake client: parameter sets per model family, routing output,
and what happens when the service refuses or is unavailable. No network, no credentials."""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from planwerk.assistant.llm import REASONING_TOKEN_BUDGET, AzureOpenAIProvider

REQ = httpx.Request("POST", "https://example.invalid/openai/v1/chat/completions")


def _error(cls, status: int, message: str, code: str | None = None):
    return cls(message, response=httpx.Response(status, request=REQ), body={"message": message, "code": code})


def _tool_response(args: dict):
    call = SimpleNamespace(function=SimpleNamespace(name="route_question", arguments=json.dumps(args)))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
                           usage=SimpleNamespace(prompt_tokens=500, completion_tokens=40))


def _text_response(text: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None, content=text))],
                           usage=SimpleNamespace(prompt_tokens=700, completion_tokens=120))


class FakeClient:
    """Plays back a script of responses or exceptions and records every request."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


ARGS = dict(name="kpi", scope="2000", year=2025, month=6, ytd=False, kpi="db2")


@pytest.fixture(autouse=True)
def _no_azure_env(monkeypatch):
    for v in ("AZURE_OPENAI_MODEL", "AZURE_OPENAI_MODEL_FAMILY", "AZURE_OPENAI_REASONING_EFFORT"):
        monkeypatch.delenv(v, raising=False)


def test_classic_model_gets_temperature_and_max_tokens():
    c = FakeClient(_tool_response(ARGS), _text_response("Text mit {{f:ist}}"))
    p = AzureOpenAIProvider(client=c, deployment="gpt-4o-mini")
    i = p.route_model("Wie steht Österreich im Juni da?", (2025, 12), {"2100": "Vertrieb AT"})
    assert (i.name, i.scope, i.year, i.month, i.kpi, i.month_given) == ("kpi", "2000", 2025, 6, "db2", True)
    assert p.rewrite("system", "user", "Entwurf") == "Text mit {{f:ist}}"
    route, rewrite = c.requests
    assert route["temperature"] == 0 and route["max_tokens"] == 300 and "max_completion_tokens" not in route
    assert route["tool_choice"]["function"]["name"] == "route_question"
    assert "2100 Vertrieb AT" in route["messages"][0]["content"]
    assert rewrite["temperature"] == 0.2 and rewrite["max_tokens"] == 600
    assert (p.usage.calls, p.usage.prompt_tokens, p.usage.completion_tokens, p.usage.fallbacks) == (2, 1200, 160, 0)
    assert (p.usage.rule_routed, p.usage.model_routed) == (0, 1)


@pytest.mark.parametrize("deployment", ["gpt-5-mini", "GPT-5-nano", "o4-mini"])
def test_reasoning_model_gets_max_completion_tokens_and_no_temperature(deployment):
    c = FakeClient(_text_response("ok"))
    AzureOpenAIProvider(client=c, deployment=deployment).rewrite("s", "u", "d")
    (req,) = c.requests
    assert "temperature" not in req and "max_tokens" not in req
    assert req["max_completion_tokens"] == 600 + REASONING_TOKEN_BUDGET and req["reasoning_effort"] == "low"


def test_family_is_corrected_when_the_deployment_name_does_not_tell():
    reject = _error(openai.BadRequestError, 400, "Unsupported parameter: 'max_tokens' is not supported with this "
                                                 "model. Use 'max_completion_tokens' instead.", "unsupported_parameter")
    c = FakeClient(reject, _text_response("ok"), _text_response("ok"))
    p = AzureOpenAIProvider(client=c, deployment="planwerk-prod")  # a reasoning model behind a neutral name
    assert p.rewrite("s", "u", "d") == "ok" and p.reasoning
    assert "max_tokens" in c.requests[0] and "max_completion_tokens" in c.requests[1]
    p.rewrite("s", "u", "d")  # stays corrected: no second rejected call
    assert len(c.requests) == 3 and "max_completion_tokens" in c.requests[2]


def test_reasoning_effort_is_dropped_when_rejected():
    reject = _error(openai.BadRequestError, 400, "Unrecognized request argument supplied: reasoning_effort")
    c = FakeClient(reject, _text_response("ok"))
    p = AzureOpenAIProvider(client=c, deployment="gpt-5-mini")
    assert p.rewrite("s", "u", "d") == "ok"
    assert "reasoning_effort" in c.requests[0] and "reasoning_effort" not in c.requests[1]


def test_rate_limit_after_retries_falls_back_and_is_counted():
    limit = _error(openai.RateLimitError, 429, "Requests have exceeded the token rate limit")
    c = FakeClient(limit, limit)
    p = AzureOpenAIProvider(client=c, deployment="gpt-5-mini")
    # the rules know this question: no model call, so the outage does not matter
    i = p.route("Wie hoch war der Umsatz in Polen im März 2025?", (2025, 12), {})
    assert (i.name, i.scope, i.month, i.kpi) == ("kpi", "3000", 3, "umsatz") and c.requests == []
    # the rules cannot place this one and the model is unreachable: out of scope, and counted
    assert p.route("Wie ist die Auftragslage in Österreich im Dezember 2025?", (2025, 12), {}).name == "out_of_scope"
    assert p.rewrite("s", "u", "Entwurf {{f:ist}}") == "Entwurf {{f:ist}}"
    assert (p.usage.fallbacks, p.usage.calls, p.usage.rule_routed, p.usage.model_routed) == (2, 0, 1, 0)


def test_content_filter_on_the_question_is_out_of_scope():
    blocked = _error(openai.BadRequestError, 400, "The response was filtered due to the prompt triggering Azure "
                                                  "OpenAI's content management policy.", "content_filter")
    p = AzureOpenAIProvider(client=FakeClient(blocked), deployment="gpt-4o-mini")
    assert p.route_model("...", (2025, 12), {}).name == "out_of_scope"
    assert p.usage.fallbacks == 0


@pytest.mark.parametrize("response", [_text_response("Ich rufe kein Werkzeug auf."), _tool_response({**ARGS, "scope": "9999"}),
                                      _tool_response({**ARGS, "name": "drop_table"})])
def test_malformed_routing_never_reaches_sql(response):
    """No tool call, a scope outside the vocabulary or an unknown intent: the provider raises or the intent fails
    validation, and the graph answers 'out of scope'."""
    p = AzureOpenAIProvider(client=FakeClient(response), deployment="gpt-4o-mini")
    with pytest.raises(Exception):  # noqa: B017 - any failure is fine, the graph catches all of them
        p.route_model("frage", (2025, 12), {}).validated(set())


def test_empty_or_truncated_wording_keeps_the_draft():
    p = AzureOpenAIProvider(client=FakeClient(_text_response(None), _text_response("  ")), deployment="gpt-5-mini")
    assert p.rewrite("s", "u", "Entwurf") == "Entwurf"
    assert p.rewrite("s", "u", "Entwurf") == "Entwurf"


def test_model_name_from_the_environment_decides_the_family(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-5-mini")
    c = FakeClient(_text_response("ok"))
    AzureOpenAIProvider(client=c, deployment="planwerk-chat").rewrite("s", "u", "d")
    assert "max_completion_tokens" in c.requests[0]
