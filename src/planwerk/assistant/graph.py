"""LangGraph state machine of the assistant (ADR-0004).

    guard_input -> route -> authorise -> query -> draft -> rewrite -> verify --ok--> finish
                                                              ^           |
                                                              +--retry----+ (once, then offline draft)

Short-circuits: blocked input, out-of-scope questions, missing permission and empty results go
straight to ``finish`` with a fixed, number-free answer. Every request is audit-logged.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from planwerk.assistant import audit, commentary, guardrails, knowledge, tools, writer
from planwerk.assistant.facts import FactSheet
from planwerk.assistant.formatting import parse_numbers
from planwerk.assistant.intents import Intent, consistent
from planwerk.assistant.llm import get_provider
from planwerk.assistant.verifier import verify
from planwerk.warehouse import connect

AS_OF = (2025, 12)
MAX_REWRITES = 2


class State(TypedDict, total=False):
    question: str
    user: str
    intent: Intent
    result: Any
    sheet: FactSheet
    draft: str
    text: str
    answer: str
    attempts: int
    verified: bool
    unverified: list[str]
    status: str  # answered | blocked | out_of_scope | denied | no_data | fallback | error
    block_category: str | None
    sql: list[str]
    fallback_used: bool


class Assistant:
    def __init__(self, provider=None, con=None, as_of: tuple[int, int] = AS_OF, audit_log: bool = True):
        self.provider = provider or get_provider()
        self.con = con or connect(read_only=True)
        self.as_of = as_of
        self.audit_log = audit_log
        tools.set_user(self.con, "controller")
        self.cc_names = tools.cost_centre_names(self.con)
        self.index = knowledge.get_index()
        self.graph = self._build()

    # ---- nodes ---------------------------------------------------------------------------------
    def _guard(self, s: State) -> State:
        g = guardrails.check_input(s["question"])
        if g.blocked:
            return dict(status="blocked", block_category=g.category, answer=g.message)
        return {}

    def _route(self, s: State) -> State:
        try:
            i = self.provider.route(s["question"], self.as_of, self.cc_names)
            i = i.validated(set(self.cc_names))
            if not consistent(s["question"], i):
                i = Intent(name="out_of_scope")
            if i.name == "method" and not knowledge.in_scope(s["question"]):
                i = Intent(name="out_of_scope")  # decided locally, whatever model or search service ranks
        except Exception:  # an invalid routing never reaches SQL
            i = Intent(name="out_of_scope")
        if i.name == "out_of_scope":
            return dict(intent=i, status="out_of_scope", answer=writer.OUT_OF_SCOPE)
        if (i.year, i.month) > self.as_of:
            i = replace(i, year=self.as_of[0], month=self.as_of[1])
        return dict(intent=i)

    def _authorise(self, s: State) -> State:
        try:
            tools.authorise(s["user"], s["intent"])
        except tools.AccessDenied as e:
            return dict(status="denied", answer=str(e))
        return {}

    def _query(self, s: State) -> State:
        i = s["intent"]
        tools.set_user(self.con, s["user"])  # row-level security in the views uses this
        if i.name == "method":
            return self._documents(s)
        try:
            if i.name == "commentary":
                scope = i.scope
                month = i.month if i.month_given else self.as_of[1]
                ci = commentary.build(self.con, scope, i.year, month)
                return dict(sheet=ci.sheet, draft=ci.draft, sql=ci.sql, result=ci)
            res = tools.TOOLS[i.name](self.con, i)
        finally:
            tools.set_user(self.con, "controller")
        if res.empty:
            return dict(status="no_data", answer=writer.no_data(i), sql=res.sql)
        return dict(result=res, sheet=res.sheet, sql=res.sql, draft=writer.offline_answer(i, res))

    def _documents(self, s: State) -> State:
        """Method questions: passages from the document index; numbers allowed only if they are in them."""
        hits = self.index.search(s["question"], top=3) or knowledge.local_index().search(s["question"], top=3)
        if not hits:
            return dict(status="out_of_scope", answer=writer.OUT_OF_SCOPE)
        sheet = FactSheet()
        for h in hits:
            for k, t in enumerate(parse_numbers(h.chunk.heading + "\n" + h.chunk.text)):
                unit = {"EUR": "EUR", "PCT": "PCT"}.get(t.unit, "DEC")
                sheet.add(f"doc_{len(sheet.facts)}_{k}", f"Zahl aus {h.chunk.source}", t.value, unit, h.chunk.id)
                sheet.allowed_tokens.add(t.text.lstrip("+-−").strip())
        draft = knowledge.best_sentences(s["question"], hits)
        return dict(result=hits, sheet=sheet, sql=[f"search:{self.index.name}"], draft=draft)

    def _rewrite(self, s: State) -> State:
        attempts = s.get("attempts", 0)
        draft = s["draft"]
        if attempts >= MAX_REWRITES or self.provider.name == "offline":
            template, fallback = draft, attempts >= MAX_REWRITES
        else:
            i = s["intent"]
            if i.name == "commentary":
                system, user = commentary.COMMENTARY_SYSTEM_PROMPT, commentary.user_prompt(s["result"])
            elif i.name == "method":
                system, user = writer.METHOD_SYSTEM_PROMPT, writer.method_user_prompt(s["question"], s["result"])
            else:
                system, user = writer.LLM_SYSTEM_PROMPT, writer.llm_user_prompt(s["question"], i, s["result"], draft)
            template, fallback = self.provider.rewrite(system, user, draft), False
        try:
            text = s["sheet"].render(template)
        except KeyError:  # model invented a fact id
            text = None
        return dict(text=text, attempts=attempts + 1, fallback_used=fallback or s.get("fallback_used", False))

    def _verify(self, s: State) -> State:
        text = s.get("text")
        if text is None:
            return dict(verified=False, unverified=["<unknown fact id>"])
        v = verify(text, s["sheet"])
        out = guardrails.check_output(text)
        ok = v.ok and not out.blocked
        return dict(verified=ok, unverified=v.unverified + ([out.category] if out.blocked else []))

    def _after_verify(self, s: State) -> str:
        if s["verified"]:
            return "finish"
        return "rewrite" if s.get("attempts", 0) <= MAX_REWRITES else "finish"

    def _finish(self, s: State) -> State:
        if s.get("status"):
            return {}
        if s.get("verified"):
            answer = s["text"]
            if s["intent"].name == "method":
                hits = s["result"]
                if answer.strip() == writer.NO_DOC_ANSWER:
                    return dict(status="out_of_scope", answer=answer)
                answer += "\n\nQuelle: " + "; ".join(dict.fromkeys(knowledge.cite(h) for h in hits[:2]))
            return dict(status="fallback" if s.get("fallback_used") else "answered", answer=answer)
        return dict(status="error", answer="Die Antwort konnte nicht mit geprüften Zahlen erstellt werden.")

    # ---- graph ---------------------------------------------------------------------------------
    def _build(self):
        g = StateGraph(State)
        for name, fn in (("guard", self._guard), ("route", self._route), ("authorise", self._authorise),
                         ("query", self._query), ("rewrite", self._rewrite), ("verify", self._verify),
                         ("finish", self._finish)):
            g.add_node(name, fn)
        g.set_entry_point("guard")
        stop = lambda s: "finish" if s.get("status") else "next"  # noqa: E731
        g.add_conditional_edges("guard", stop, {"finish": "finish", "next": "route"})
        g.add_conditional_edges("route", stop, {"finish": "finish", "next": "authorise"})
        g.add_conditional_edges("authorise", stop, {"finish": "finish", "next": "query"})
        g.add_conditional_edges("query", stop, {"finish": "finish", "next": "rewrite"})
        g.add_edge("rewrite", "verify")
        g.add_conditional_edges("verify", self._after_verify, {"finish": "finish", "rewrite": "rewrite"})
        g.add_edge("finish", END)
        return g.compile()

    # ---- public API ----------------------------------------------------------------------------
    def ask(self, question: str, user: str = "controller") -> dict:
        t0 = time.perf_counter()
        u0 = (self.provider.usage.prompt_tokens, self.provider.usage.completion_tokens)
        s: State = self.graph.invoke({"question": question, "user": user})
        p_tok = self.provider.usage.prompt_tokens - u0[0]
        c_tok = self.provider.usage.completion_tokens - u0[1]
        from planwerk.assistant.llm import Usage
        cost = Usage(p_tok, c_tok).cost_eur()
        i = s.get("intent")
        out = dict(answer=s["answer"], status=s["status"], intent=i.to_dict() if i else None,
                   facts=s["sheet"].to_list() if s.get("sheet") else [], sql=s.get("sql", []),
                   verified=bool(s.get("verified")), unverified=s.get("unverified", []),
                   block_category=s.get("block_category"), provider=self.provider.name,
                   prompt_tokens=p_tok, completion_tokens=c_tok, cost_eur=round(cost, 6),
                   latency_ms=round((time.perf_counter() - t0) * 1000, 1), attempts=s.get("attempts", 0))
        if self.audit_log:
            role = tools.access_list().get(user, {}).get("role")
            audit.write(dict(user=user, role=role, question=question, answer=out["answer"],
                             **{k: out[k] for k in ("status", "intent", "sql", "verified", "unverified",
                                                    "block_category", "provider", "prompt_tokens",
                                                    "completion_tokens", "cost_eur", "latency_ms", "attempts")},
                             fact_ids=[f["id"] for f in out["facts"]]))
        return out

    def commentary(self, scope: str, year: int, month: int, user: str = "controller") -> dict:
        from planwerk.assistant.intents import MONTH_TEXT, SCOPE_TEXT
        q = f"Schreibe den Monatskommentar für {SCOPE_TEXT[scope]} {MONTH_TEXT[month]} {year}"
        intent = Intent(name="commentary", scope=scope, year=year, month=month, month_given=True).validated()
        t0 = time.perf_counter()
        try:
            tools.authorise(user, intent)
        except tools.AccessDenied as e:
            return dict(answer=str(e), status="denied", verified=False, facts=[], unverified=[])
        s = self._query({"question": q, "user": user, "intent": intent})
        s.update(question=q, user=user, intent=intent)
        while True:
            s.update(self._rewrite(s))
            s.update(self._verify(s))
            if self._after_verify(s) == "finish":
                break
        s.update(self._finish(s))
        out = dict(answer=s["answer"], status=s["status"], verified=bool(s["verified"]),
                   unverified=s.get("unverified", []), facts=s["sheet"].to_list(), sql=s["sql"], draft=s["draft"],
                   provider=self.provider.name, latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        if self.audit_log:
            audit.write(dict(user=user, question=q, answer=out["answer"], status=out["status"],
                             verified=out["verified"], unverified=out["unverified"], provider=out["provider"],
                             fact_ids=[f["id"] for f in out["facts"]], latency_ms=out["latency_ms"]))
        return out


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Planwerk Controlling-Assistent (simulierte Daten)")
    ap.add_argument("question", nargs="*")
    ap.add_argument("--user", default="controller")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--commentary", metavar="SCOPE:YYYY-MM")
    a = ap.parse_args(argv)
    asst = Assistant(get_provider(a.provider))
    if a.commentary:
        scope, per = a.commentary.split(":")
        r = asst.commentary(scope, int(per[:4]), int(per[5:7]), a.user)
    else:
        r = asst.ask(" ".join(a.question), a.user)
    print(r["answer"])
    print(f"\n[{r['status']}, verified={r['verified']}, {r.get('latency_ms')} ms]")


if __name__ == "__main__":
    main()
