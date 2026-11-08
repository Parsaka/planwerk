"""Append-only audit log (JSON Lines) for every assistant request.

Logged: who asked what, which intent and SQL ran, which facts were used, whether the
verifier passed, provider, tokens, cost and latency. Not logged: query results beyond fact ids
(the warehouse is the system of record). The question text is stored because it is business
content of authorised users; ``PLANWERK_AUDIT_REDACT=1`` stores only its hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from planwerk.generator.config import REPO_ROOT


def log_path() -> Path:
    return Path(os.environ.get("PLANWERK_AUDIT_LOG", REPO_ROOT / "data" / "audit" / "assistant_audit.jsonl"))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(entry: dict) -> dict:
    e = dict(entry)
    e.setdefault("request_id", str(uuid.uuid4()))
    e["ts"] = datetime.now(UTC).isoformat(timespec="milliseconds")
    q = e.get("question", "")
    e["question_sha256"] = sha(q)
    if os.environ.get("PLANWERK_AUDIT_REDACT") == "1":
        e["question"] = None
    if "answer" in e:
        e["answer_sha256"] = sha(e.pop("answer") or "")
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    return e
