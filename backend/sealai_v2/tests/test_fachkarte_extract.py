"""Offline tests for Fachkarten-Ingestion (Paperless path) — fake client, no API. Locks the doctrine:
ALL-draft output (the review queue), schema-faithful seed entry, fail-safe, doc-grounded only."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.fachkarte_extract import FachkarteExtractor
from sealai_v2.prompts.assembler import FachkarteExtractPromptAssembler


class _FakeClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def generate(self, *, system, user, model_config, **_kw):
        self.calls += 1
        self.last_user = user
        return SimpleNamespace(text=self._text)


_CFG = ModelConfig(model="fake", temperature=0.0)
_GOOD = """{
  "titel_vorschlag": "EPDM in Heißwasser/Dampf",
  "scope": {"material": ["EPDM"], "medium": ["Heißwasser", "Dampf"],
            "property": ["Hydrolysebeständigkeit"], "application": []},
  "claims": ["EPDM ist für Heißwasser und Dampf geeignet.",
             "In Mineralöl quillt EPDM stark."]
}"""


def _extractor(text):
    c = _FakeClient(text)
    return FachkarteExtractor(c, FachkarteExtractPromptAssembler(), _CFG), c


def test_extracts_all_draft_seed_entry():
    x, _c = _extractor(_GOOD)
    draft = asyncio.run(x.extract("…Datenblatt-Text…", source="paperless#42"))
    assert draft is not None and not draft.empty
    entry = draft.to_seed_entry()
    assert entry["review_state"] == "draft"
    assert all(
        c["review_state"] == "draft" for c in entry["claims"]
    )  # never authoritative
    assert entry["id"].startswith("FK-DRAFT-")
    assert entry["scope"]["material"] == ["EPDM"]
    assert any("paperless-draft:paperless#42" in p for p in entry["provenance"])
    assert len(entry["claims"]) == 2


def test_handles_array_wrapped_and_fenced_response():
    """Mistral Small often returns the card inside a ```json [ ... ] array — the parser unwraps it."""
    wrapped = "```json\n[\n" + _GOOD + "\n]\n```"
    x, _c = _extractor(wrapped)
    draft = asyncio.run(x.extract("doc", source="s"))
    assert draft is not None and len(draft.claims) == 2


def test_fail_safe_bad_json_returns_none():
    x, _c = _extractor("kein JSON")
    assert asyncio.run(x.extract("text", source="s")) is None


def test_no_claims_returns_none():
    x, _c = _extractor('{"titel_vorschlag":"x","scope":{},"claims":[]}')
    assert asyncio.run(x.extract("text", source="s")) is None


def test_empty_doc_is_inert():
    x, c = _extractor(_GOOD)
    assert asyncio.run(x.extract("   ", source="s")) is None and c.calls == 0


def test_doc_is_truncated_to_cap():
    x, c = _extractor(_GOOD)
    asyncio.run(x.extract("A" * 20000, source="s"))
    assert len(c.last_user) <= 12000  # cost/context bound


def test_prompt_renders_doctrine():
    p = FachkarteExtractPromptAssembler().fachkarte_extract_prompt()
    assert "DRAFT" in p and "Erfinde nichts" in p and "JSON" in p


def test_draft_entry_parses_as_draft_fachkarte():
    """Schema-faithfulness: the produced seed entry parses through the real Fachkarten parser as a
    DRAFT card (provisional channel), proving a reviewed promotion is a pure edit."""
    from sealai_v2.knowledge.fachkarten import _card

    x, _c = _extractor(_GOOD)
    entry = asyncio.run(x.extract("doc", source="s")).to_seed_entry()
    card = _card(entry)
    assert card.review_state == "draft" and len(card.draft_claims()) == 2
    assert len(card.reviewed_claims()) == 0  # nothing authoritative until owner review


def test_chunks_splits_large_doc_at_paragraphs():
    from sealai_v2.core.fachkarte_extract import _MAX_DOC_CHARS, _chunks

    assert _chunks("kurz") == ["kurz"]
    big = ("Absatz " + "x" * 4000 + "\n\n") * 5  # ~20k over 5 paragraphs
    cs = _chunks(big)
    assert len(cs) >= 2 and all(len(c) <= _MAX_DOC_CHARS for c in cs)


class _CyclingFake:
    """Returns a different scripted response per call — to exercise the multi-chunk merge."""

    def __init__(self, texts) -> None:
        self._texts = texts
        self.calls = 0

    async def generate(self, *, system, user, model_config, **_kw):
        t = self._texts[self.calls % len(self._texts)]
        self.calls += 1
        return SimpleNamespace(text=t)


def test_extract_document_merges_and_dedupes_chunks():
    from sealai_v2.core.fachkarte_extract import FachkarteExtractor

    a = '{"titel_vorschlag":"FFKM","scope":{"material":["FFKM"]},"claims":["claim A","shared"]}'
    b = '{"titel_vorschlag":"X","scope":{"material":["FFKM"],"medium":["Säure"]},"claims":["claim B","shared"]}'
    big = ("p" * 8000 + "\n\n") * 2  # forces 2 chunks (>12k)
    x = FachkarteExtractor(
        _CyclingFake([a, b]), FachkarteExtractPromptAssembler(), _CFG
    )
    draft = asyncio.run(x.extract_document(big, source="s"))
    assert set(draft.claims) == {"claim A", "claim B", "shared"}  # union, de-duped
    assert "Säure" in draft.scope["medium"]  # scope unioned across chunks
    assert draft.titel == "FFKM"  # from the first chunk
