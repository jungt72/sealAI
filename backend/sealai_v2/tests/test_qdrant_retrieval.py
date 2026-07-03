from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.qdrant_retrieval import (
    GLOBAL_TENANT,
    OpenAiEmbedder,
    QdrantFachkartenRetriever,
    _hits_to_result,
    _make_embedder,
    _quelle,
    _select_points_with_reviewed_backfill,
    claim_points,
)
from sealai_v2.knowledge.retrieval import _quelle as inproc_quelle


class _FakePoint:
    def __init__(self, payload: dict, score: float | None = None) -> None:
        self.payload = payload
        self.score = score


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


def test_reviewed_backfill_preserves_top_k_and_adds_close_reviewed_tail():
    pts = [
        _FakePoint(
            {
                "review_state": "draft",
                "card_id": f"draft-{idx}",
                "scope": {"material": ["PTFE"]},
            },
            1.0 - idx * 0.02,
        )
        for idx in range(5)
    ]
    close_reviewed = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "scope": {"material": ["PTFE"]},
        },
        0.78,
    )
    weak_reviewed = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-WEAK",
            "scope": {"material": ["PTFE"]},
        },
        0.40,
    )
    selected = _select_points_with_reviewed_backfill(
        [*pts, close_reviewed, weak_reviewed], k=5, query="Informationen zu PTFE"
    )

    assert selected[:5] == pts
    assert close_reviewed in selected
    assert weak_reviewed not in selected


def test_reviewed_backfill_prefers_matching_material_scope_for_material_queries():
    pts = [
        _FakePoint(
            {
                "review_state": "draft",
                "card_id": f"draft-{idx}",
                "scope": {"material": ["PTFE"]},
            },
            1.0 - idx * 0.02,
        )
        for idx in range(5)
    ]
    vmq_ptfe_lip = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-VMQ-DYNAMISCH",
            "scope": {"material": ["VMQ"]},
        },
        0.80,
    )
    ptfe_card = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "scope": {"material": ["PTFE"]},
        },
        0.78,
    )

    selected = _select_points_with_reviewed_backfill(
        [*pts, vmq_ptfe_lip, ptfe_card], k=5, query="Informationen zu PTFE"
    )

    assert ptfe_card in selected
    assert vmq_ptfe_lip not in selected


def test_reviewed_backfill_is_noop_when_top_k_already_has_reviewed():
    reviewed = _FakePoint({"review_state": "reviewed", "card_id": "FK-REVIEWED"}, 0.9)
    extra = _FakePoint({"review_state": "reviewed", "card_id": "FK-EXTRA"}, 0.89)
    pts = [_FakePoint({"review_state": "draft"}, 1.0), reviewed, extra]

    assert _select_points_with_reviewed_backfill(pts, k=2) == pts[:2]


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
        assert text and not text.startswith(
            ("passage: ", "query: ")
        )  # RAW; prefix applied at embed
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


class _S:
    """Minimal settings stand-in for the embedder factory (no env_prefix machinery needed)."""

    embed_provider = "openai"
    embed_model = "text-embedding-3-small"
    embed_cache_dir = None


def test_make_embedder_selects_openai_api_path(monkeypatch):
    """embed_provider=openai → the API embedder (NO local model → NO RAM/OOM); key from the env."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    emb = _make_embedder(_S())  # constructs the client lazily; no network until .embed
    assert isinstance(emb, OpenAiEmbedder)


def test_make_embedder_openai_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _make_embedder(_S())
