# ADR-0004: Fact-first AI assistant (the model never computes figures)

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

Language models make arithmetic and recall errors. A controlling commentary with a single
wrong number is worse than none: the CFO stops trusting the tool. Q3 (ADR-0001) demands 100 %
correct figures.

## Decision

1. Figures come only from **read-only SQL on semantic views** (`semantic.*`). SQL is generated
   from a whitelist of intents with parameters, or, for free questions, validated with
   `sqlglot` (SELECT only, allowed views only, row limit) before execution.
2. The model receives a **fact sheet** (ids, values, units) and must reference every number by
   fact id. The renderer replaces ids with German-formatted values.
3. A **verifier** parses every number in the final text (German format: 1.234,5; 3,2 %;
   1,2 Mio. EUR) and checks it against the fact sheet. Unverified numbers block the answer.
4. The orchestration is a small **LangGraph** state machine: classify -> plan query ->
   validate -> execute -> draft -> verify -> (retry once | answer).
5. The LLM provider is pluggable (Azure OpenAI per the target architecture; an offline
   deterministic writer for CI and for runs without credentials).

## Consequences

- CI can test the whole pipeline without an API key; the model-quality part of the eval runs
  when `AZURE_OPENAI_*` secrets are present.
- Commentary style is limited by the fact sheet: the model can explain, not invent.
