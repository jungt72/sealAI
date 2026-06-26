"""Fachkarten-Ingestion (build-spec §3 Paperless path, Phase 1) — light LLM extraction of a DRAFT
Fachkarte from a source document (Paperless export, datasheet, pasted text).

DOCTRINE (keine Halluzinationen + the vorläufig→reviewed gate): the produced card is
``review_state="draft"`` with EVERY claim draft + provenance naming the source doc. The in-process
retriever surfaces draft claims as 'vorläufig' (never authoritative, never corrective). It becomes
authoritative ONLY after the OWNER reviews + promotes it (claim review_state → 'reviewed', adds a
primary source / owner provenance, merges into ``fachkarten_seed.json``). So this stage NEVER writes
prod knowledge — it fills a REVIEW QUEUE. Conservative like the distiller: ONLY doc-grounded claims,
no fabrication, no added general knowledge; a parse/LLM failure yields NOTHING. Pure orchestration over
the injected helper client — the document text is the only input, nothing leaves except via the client.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

from sealai_v2.core.contracts import LlmClient, ModelConfig

_MAX_CLAIMS = 8
_MAX_TAGS = 8
_MAX_CLAIM_LEN = 300
_MAX_DOC_CHARS = (
    12000  # cap ONE helper call (cost + "lost in the middle"); large docs are CHUNKED
)
_MAX_MERGED_CLAIMS = (
    24  # a chunked doc's merged card cap (deep-research docs yield many claims)
)
_SCOPE_DIMS = ("material", "medium", "property", "application")


def _chunks(text: str, size: int = _MAX_DOC_CHARS) -> list[str]:
    """Split a long document into <=``size`` pieces at paragraph boundaries (so a claim is not cut
    mid-sentence), hard-splitting any single oversized paragraph. Short docs → one chunk."""
    if len(text) <= size:
        return [text]
    out: list[str] = []
    cur = ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) + 2 > size:
            out.append(cur)
            cur = ""
        cur = (cur + "\n\n" + para) if cur else para
        while len(cur) > size:
            out.append(cur[:size])
            cur = cur[size:]
    if cur.strip():
        out.append(cur)
    return out


class FachkarteExtractPrompt(Protocol):
    def fachkarte_extract_prompt(self) -> str: ...


def _extract_json(raw: str) -> str:
    """Pull the outermost JSON value (object OR array — the helper sometimes wraps the card in a
    ``[ ... ]`` and/or ```json fences), tolerating code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    s = s.strip()
    starts = [p for p in (s.find("{"), s.find("[")) if p != -1]
    if not starts:
        return s
    start = min(starts)
    end = max(s.rfind("}"), s.rfind("]"))
    return s[start : end + 1] if end > start else s


def _clean_list(value, limit: int, max_len: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        t = " ".join(item.split())[:max_len].strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
        if len(out) >= limit:
            break
    return tuple(out)


def _slug(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    norm = re.sub(r"[^A-Za-z0-9]+", "-", norm).strip("-").upper()
    return norm[:40] or "UNBENANNT"


@dataclass(frozen=True)
class FachkarteDraft:
    """A draft Fachkarte awaiting owner review. ``to_seed_entry`` renders the canonical seed-JSON shape
    (all-draft) so a reviewed promotion is a pure edit (flip review_state, add a primary source)."""

    id: str
    titel: str
    source: str
    scope: dict
    claims: tuple[str, ...] = ()
    provenance: tuple[str, ...] = field(default_factory=tuple)

    @property
    def empty(self) -> bool:
        return not self.claims

    def to_seed_entry(self) -> dict:
        prov = list(self.provenance)
        return {
            "id": self.id,
            "review_state": "draft",
            "provenance": prov,
            "version": "paperless-draft-v0",
            "matrix_crosscheck": "unchecked",
            "titel": self.titel,
            "scope": {dim: list(self.scope.get(dim, ())) for dim in _SCOPE_DIMS},
            "claims": [
                {"text": t, "review_state": "draft", "provenance": prov}
                for t in self.claims
            ],
        }


class FachkarteExtractor:
    """Extracts a DRAFT Fachkarte from a document via the helper LLM. Fails safe (None on any error /
    no doc-grounded claim). Source-agnostic: the caller supplies the document TEXT (Paperless export,
    datasheet, pasted) + a ``source`` label for provenance."""

    def __init__(
        self,
        client: LlmClient,
        assembler: FachkarteExtractPrompt,
        model_config: ModelConfig,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config

    async def extract(self, doc_text: str, *, source: str) -> FachkarteDraft | None:
        text = (doc_text or "").strip()
        source = (source or "unbekannt").strip()
        if not text:
            return None
        try:
            res = await self._client.generate(
                system=self._assembler.fachkarte_extract_prompt(),
                user=text[:_MAX_DOC_CHARS],
                model_config=self._model_config,
            )
            data = json.loads(_extract_json(res.text))
            if isinstance(
                data, list
            ):  # the helper sometimes wraps the card in a 1-element array
                data = next((x for x in data if isinstance(x, dict)), None)
            if not isinstance(data, dict):
                raise ValueError("extraction did not return a JSON object")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None  # fail safe — never a guessed card

        claims = _clean_list(data.get("claims"), _MAX_CLAIMS, _MAX_CLAIM_LEN)
        if not claims:
            return None  # nothing doc-grounded → no card
        raw_scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
        scope = {
            dim: _clean_list(raw_scope.get(dim), _MAX_TAGS, 60) for dim in _SCOPE_DIMS
        }
        titel = " ".join(str(data.get("titel_vorschlag", "")).split())[:120] or source
        return FachkarteDraft(
            id=f"FK-DRAFT-{_slug(titel)}",
            titel=titel,
            source=source,
            scope=scope,
            claims=claims,
            provenance=(f"paperless-draft:{source}",),
        )

    async def extract_document(
        self, doc_text: str, *, source: str
    ) -> FachkarteDraft | None:
        """Thorough extraction for a FULL document: chunk it, extract each chunk, MERGE into ONE card
        (union claims + scope, de-duped, capped). One document → one Fachkarte. Short docs → one call."""
        text = (doc_text or "").strip()
        if not text:
            return None
        chunks = _chunks(text)
        if len(chunks) == 1:
            return await self.extract(text, source=source)
        drafts = [
            d for d in [await self.extract(ch, source=source) for ch in chunks] if d
        ]
        if not drafts:
            return None
        claims: list[str] = []
        seen: set[str] = set()
        for d in drafts:
            for c in d.claims:
                if c.lower() not in seen:
                    seen.add(c.lower())
                    claims.append(c)
        scope = {
            dim: tuple(dict.fromkeys(t for d in drafts for t in d.scope.get(dim, ())))[
                :_MAX_TAGS
            ]
            for dim in _SCOPE_DIMS
        }
        return FachkarteDraft(
            id=f"FK-DRAFT-{_slug(drafts[0].titel)}",
            titel=drafts[0].titel,
            source=source,
            scope=scope,
            claims=tuple(claims[:_MAX_MERGED_CLAIMS]),
            provenance=(f"paperless-draft:{source}",),
        )
