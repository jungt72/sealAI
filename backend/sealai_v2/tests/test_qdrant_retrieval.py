from __future__ import annotations

import asyncio

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.qdrant_retrieval import (
    GLOBAL_TENANT,
    QdrantFachkartenRetriever,
    _hits_to_result,
    _quelle,
    claim_points,
)
from sealai_v2.knowledge.retrieval import _quelle as inproc_quelle


class _FakePoint:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


def test_hits_to_result_splits_reviewed_and_provisional():
    # Doctrine: reviewed → grounding_facts (authoritative); draft → provisional ("vorläufig").
    pts = [
        _FakePoint(
            {
                "claim_text": "EPDM ist unpolar",
                "review_state": "reviewed",
                "card_id": "FK-EPDM",
                "sources": ["DIN 1234"],
                "quelle": "Fachkarte FK-EPDM (reviewed; owner:thorsten)",
            }
        ),
        _FakePoint(
            {
                "claim_text": "VMQ breit beständig",
                "review_state": "draft",
                "card_id": "FK-VMQ",
                "sources": [],
                "quelle": "Fachkarte FK-VMQ (draft — vorläufig…)",
            }
        ),
    ]
    res = _hits_to_result(pts)
    assert len(res.grounding_facts) == 1
    gf = res.grounding_facts[0]
    assert gf.text == "EPDM ist unpolar" and gf.card_id == "FK-EPDM"
    assert gf.sources == ("DIN 1234",) and gf.kind == "card"
    assert (
        len(res.provisional) == 1 and res.provisional[0].text == "VMQ breit beständig"
    )
    assert res.grounded  # grounding_facts present


def test_claim_points_one_per_claim_with_payload():
    cat = load_fachkarten()
    pts = list(claim_points(cat))
    assert len(pts) == sum(len(c.claims) for c in cat.cards)  # one point per CLAIM
    ids = set()
    required = {
        "card_id",
        "review_state",
        "claim_text",
        "sources",
        "provenance",
        "scope",
        "tenant_id",
        "quelle",
    }
    for pid, text, payload in pts:
        assert text.startswith("passage: ")  # e5 passage prefix
        assert required <= set(payload)
        assert payload["tenant_id"] == GLOBAL_TENANT
        assert payload["review_state"] in ("reviewed", "draft")
        ids.add(pid)
    assert len(ids) == len(pts)  # unique → idempotent upsert keys
    reviewed = [p for _i, _t, p in pts if p["review_state"] == "reviewed"]
    assert reviewed and all("reviewed" in p["quelle"] for p in reviewed)
    drafts = [p for _i, _t, p in pts if p["review_state"] == "draft"]
    assert all("vorläufig" in p["quelle"] for p in drafts)


def test_retrieve_rejects_blank_tenant():
    # The mandatory-tenant guard fires BEFORE any qdrant import (so it is testable dep-free).
    r = QdrantFachkartenRetriever(Settings(), client=object(), embedder=object())
    raised = False
    try:
        asyncio.run(r.retrieve("frage", tenant_id="  "))
    except ValueError as e:
        raised = "tenant_id" in str(e)
    assert raised


def test_build_retriever_default_and_url_guard():
    from sealai_v2.knowledge.retrieval import InProcessRetriever
    from sealai_v2.pipeline.pipeline import _build_retriever

    # default backend → in-process (no embedder load)
    assert isinstance(
        _build_retriever(Settings(retriever_backend="in_process")), InProcessRetriever
    )
    # qdrant requested but no url → in-process (the url guard, no embedder load)
    assert isinstance(
        _build_retriever(Settings(retriever_backend="qdrant", qdrant_url=None)),
        InProcessRetriever,
    )


def test_build_retriever_failsafe_on_construction_error(monkeypatch):
    # qdrant requested + url set, but construction fails (missing dep / unreachable Qdrant) → the
    # pipeline must fall back to in-process, never crash startup.
    import sealai_v2.knowledge.qdrant_retrieval as qr
    from sealai_v2.knowledge.retrieval import InProcessRetriever
    from sealai_v2.pipeline.pipeline import _build_retriever

    def _boom(*a, **k):
        raise RuntimeError("simulated unavailable dep / unreachable qdrant")

    monkeypatch.setattr(qr, "QdrantFachkartenRetriever", _boom)
    r = _build_retriever(
        Settings(retriever_backend="qdrant", qdrant_url="http://qdrant:6333")
    )
    assert isinstance(r, InProcessRetriever)  # fail-safe fallback, no crash


def test_quelle_byte_identical_to_in_process():
    # The qdrant adapter's citations must match the in-process retriever's for the same card.
    card = load_fachkarten().cards[0]
    assert _quelle(card.id, card.provenance, reviewed=True) == inproc_quelle(
        card, reviewed=True
    )
    assert _quelle(card.id, card.provenance, reviewed=False) == inproc_quelle(
        card, reviewed=False
    )
