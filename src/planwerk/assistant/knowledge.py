"""Document search over the project's German controlling and governance documents (RAG).

Answers method questions ("Wie wird der Mixeffekt berechnet?", "Wer darf alle Kostenstellen
sehen?") from the Fachkonzept, Lastenheft, governance documents and runbook, always with the
source section. Two backends with the same interface:

* ``LocalIndex`` (default, offline, used in CI): BM25 over heading-based chunks.
* ``AzureSearchIndex``: the same chunks in an Azure AI Search index (BM25 with the German
  Microsoft analyzer), signed in with Entra ID only (no API key).

Whether a question is in scope at all is decided locally and deterministically
(:func:`in_scope`), whatever backend ranks the passages, so a model or a search service can never
widen what the assistant talks about.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from planwerk.generator.config import REPO_ROOT

CORPUS = [
    "docs/fachlich/fachkonzept.md",
    "docs/fachlich/lastenheft.md",
    "docs/fachlich/zeitmessung.md",
    "docs/governance/berechtigungskonzept.md",
    "docs/governance/audit-log.md",
    "docs/governance/dsfa.md",
    "docs/governance/eu-ai-act.md",
    "docs/governance/kontrollmatrix.md",
    "docs/governance/vvt.md",
    "docs/betrieb/runbook.md",
    "docs/projekt/definition-of-done.md",
]
MAX_WORDS = 220
# Minimum BM25 score of the best passage for a question to count as in scope. Set on the dev
# questions in eval/method_dev.yaml and the out-of-scope part of the golden set, never on
# eval/method_questions.yaml.
MIN_SCORE = 4.0  # dev set: lowest in-scope 4.5, highest out-of-scope 3.4

STOPWORDS = set("""
aber alle allem allen aller alles als also am an ander andere anderen auch auf aus bei beim bin bis bist
da damit dann das dass dein deine dem den der des dessen die dies diese diesem diesen dieser dieses doch
dort du durch ein eine einem einen einer eines er es etwas euch euer für gegen gibt hab habe haben hat
hatte hier hin hinter ich ihm ihn ihnen ihr ihre im in ist ja jede jedem jeden jeder jedes jetzt kann
kein keine können man mein meine mich mir mit muss nach nicht nichts noch nun nur ob oder ohne sehr
sein seine sich sie sind so soll sollte sondern über um und uns unser unter vom von vor wann war waren
warum was weil welche welchem welchen welcher welches wenn wer werden wie wieder will wir wird wo woher
wohin womit woraus worauf zu zum zur zwischen darf dürfen gilt gelten geht macht man wofür wieso
weshalb bitte mal genau eigentlich erklär erkläre erklaer erklaere bedeutet versteht heißt heisst
hoch hoher hohe höhe viel viele wenig gross groß klein steht stehen regelt sagt
berechnet berechnen berechnung ermittelt ermitteln definiert definieren funktioniert funktionieren sehen
nutzt nutzen gehört gehören enthält enthalten pflegt gilt geregelt läuft laufen ab
""".split())


def _fold(text: str) -> str:
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return t


def _stem(w: str) -> str:
    for suf in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
        if len(w) > 4 and w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(text: str) -> list[str]:
    stop = {_fold(s) for s in STOPWORDS}
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", _fold(text)) if w not in stop and len(w) > 1]


@dataclass(frozen=True)
class Chunk:
    id: str  # "fachkonzept.md#6.2 Zerlegung"
    source: str  # file name
    heading: str  # heading path
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def _split_sections(path: Path) -> list[tuple[str, str]]:
    title, sections, current, buf = path.stem, [], None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if current is not None or buf:
                sections.append((current or title, "\n".join(buf).strip()))
            if m.group(1) == "#":
                title, current = m.group(2).strip(), m.group(2).strip()
            else:
                current = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    sections.append((current or title, "\n".join(buf).strip()))
    return [(h, t) for h, t in sections if t]


@lru_cache(maxsize=1)
def chunks() -> tuple[Chunk, ...]:
    out = []
    for rel in CORPUS:
        path = REPO_ROOT / rel
        for heading, text in _split_sections(path):
            paras, part, n = re.split(r"\n\s*\n", text), [], 0
            pieces = []
            for p in paras:
                w = len(p.split())
                if part and n + w > MAX_WORDS:
                    pieces.append("\n\n".join(part))
                    part, n = [], 0
                part.append(p)
                n += w
            if part:
                pieces.append("\n\n".join(part))
            for k, piece in enumerate(pieces):
                suffix = f" ({k + 1})" if len(pieces) > 1 else ""
                out.append(Chunk(f"{path.name}#{heading}{suffix}", path.name, heading, piece))
    return tuple(out)


class LocalIndex:
    """BM25 (k1 = 1.5, b = 0.75); the heading counts twice, so section titles carry weight."""

    name = "local_bm25"

    def __init__(self, items: tuple[Chunk, ...] | None = None) -> None:
        self.items = items or chunks()
        self.docs = [Counter(tokens(c.heading) * 2 + tokens(c.text)) for c in self.items]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _decompound(self, t: str) -> list[str]:
        """German compounds: 'mengeneffekt' -> 'menge' + 'effekt' when the parts occur in the corpus."""
        if t in self.idf or len(t) < 8:
            return [t]
        for i in range(len(t) - 4, 2, -1):
            head, tail = t[:i], t[i:]
            heads = [h for h in (head, head.rstrip("s"), _stem(head), _stem(head.rstrip("s"))) if h in self.idf]
            tails = [x for x in (tail, _stem(tail)) if x in self.idf]
            if heads and (tails or tail in self.idf):
                return [heads[0], tails[0] if tails else tail]
        return [t]

    def search(self, question: str, top: int = 3) -> list[Hit]:
        q = [p for t in tokens(question) for p in self._decompound(t)]
        scores = []
        for c, d, length in zip(self.items, self.docs, self.lengths, strict=True):
            s = 0.0
            for t in q:
                tf = d.get(t, 0)
                if tf:
                    s += self.idf[t] * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / self.avg))
            scores.append(Hit(c, s))
        return sorted((h for h in scores if h.score > 0), key=lambda h: -h.score)[:top]


@lru_cache(maxsize=1)
def local_index() -> LocalIndex:
    return LocalIndex()


def in_scope(question: str) -> bool:
    hits = local_index().search(question, top=1)
    return bool(hits) and hits[0].score >= MIN_SCORE


class AzureSearchIndex:
    """Azure AI Search over the same chunks. Needs AZURE_SEARCH_ENDPOINT and, for queries, the role
    "Search Index Data Reader" for the caller (Entra ID; API keys are not used)."""

    name = "azure_ai_search"
    INDEX = os.environ.get("AZURE_SEARCH_INDEX", "planwerk-docs")
    API = "2024-07-01"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or os.environ["AZURE_SEARCH_ENDPOINT"]).rstrip("/")
        self._cred = None

    def _headers(self) -> dict:
        from azure.identity import DefaultAzureCredential

        if self._cred is None:
            self._cred = DefaultAzureCredential()
        tok = self._cred.get_token("https://search.azure.com/.default").token
        return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        import json
        import urllib.request

        req = urllib.request.Request(f"{self.endpoint}{path}?api-version={self.API}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers=self._headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    def create_and_upload(self) -> int:
        """(Re)create the index and upload all chunks. Needs "Search Service Contributor" and
        "Search Index Data Contributor"."""
        import base64

        schema = {"name": self.INDEX, "fields": [
            {"name": "key", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "chunk_id", "type": "Edm.String", "retrievable": True},
            {"name": "source", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "heading", "type": "Edm.String", "searchable": True, "analyzer": "de.microsoft"},
            {"name": "content", "type": "Edm.String", "searchable": True, "analyzer": "de.microsoft"},
        ], "scoringProfiles": [{"name": "heading_boost", "text": {"weights": {"heading": 2, "content": 1}}}],
            "defaultScoringProfile": "heading_boost"}
        self._req("PUT", f"/indexes('{self.INDEX}')", schema)
        docs = [{"@search.action": "mergeOrUpload",
                 "key": base64.urlsafe_b64encode(c.id.encode()).decode().rstrip("="),
                 "chunk_id": c.id, "source": c.source, "heading": c.heading, "content": c.text}
                for c in chunks()]
        self._req("POST", f"/indexes('{self.INDEX}')/docs/search.index", {"value": docs})
        import time

        for _ in range(30):  # indexing is eventually consistent: wait until every chunk is searchable
            if self._req("POST", f"/indexes('{self.INDEX}')/docs/search.post.search",
                         {"search": "*", "count": True, "top": 0}).get("@odata.count", 0) >= len(docs):
                break
            time.sleep(2)
        return len(docs)

    def search(self, question: str, top: int = 3) -> list[Hit]:
        by_id = {c.id: c for c in chunks()}
        res = self._req("POST", f"/indexes('{self.INDEX}')/docs/search.post.search",
                        {"search": question, "top": top, "queryType": "simple", "searchMode": "any",
                         "select": "chunk_id"})
        return [Hit(by_id[d["chunk_id"]], float(d["@search.score"])) for d in res.get("value", [])
                if d["chunk_id"] in by_id]


def get_index(name: str | None = None):
    name = name or os.environ.get("PLANWERK_SEARCH", "auto")
    if name == "azure" or (name == "auto" and os.environ.get("AZURE_SEARCH_ENDPOINT")):
        return AzureSearchIndex()
    return local_index()


_ABBR = r"(?<!\bNr)(?<!\bAbs)(?<!\bz\. B)(?<!\bca)(?<!\bvgl)(?<!\bbzw)(?<!\bggf)(?<!\busw)(?<!\bd\. h)"


def _units(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip(" |-*")
        if not line or set(line) <= set("|-: "):
            continue
        if "|" in line:  # table row: one unit
            out.append(re.sub(r"\s*\|\s*", " · ", line).strip(" ·"))
        else:
            out += [u.strip() for u in re.split(_ABBR + r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„(])", line)]
    return [u for u in out if len(u) > 20]


def best_sentences(question: str, hits: list[Hit], n: int = 2) -> str:
    """Extractive answer from the best-ranked passage that shares terms with the question: its
    sentences or table rows with most query terms, in document order."""
    ix = local_index()

    def terms(text: str) -> set[str]:
        return {p for t in tokens(text) for p in ix._decompound(t)}

    q = terms(question)
    for h in hits:
        units = [(len(q & terms(u)), pos, u) for pos, u in enumerate(_units(h.chunk.text))]
        units = [x for x in units if x[0] > 0]
        if units:
            best = sorted(units, key=lambda x: (-x[0], x[1]))[:n]
            return " ".join(u for *_, u in sorted(best, key=lambda x: x[1]))
    return _units(hits[0].chunk.text)[0] if hits and _units(hits[0].chunk.text) else ""


def cite(hit: Hit) -> str:
    return f"{hit.chunk.source}, Abschnitt „{hit.chunk.heading}“"


__all__ = ["Chunk", "Hit", "LocalIndex", "AzureSearchIndex", "chunks", "local_index", "in_scope", "get_index",
           "best_sentences", "cite", "tokens", "MIN_SCORE"]
