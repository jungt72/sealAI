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
    _rerank_points,
    _select_points_with_reviewed_backfill,
    claim_points,
    ensure_collection,
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


def test_reviewed_backfill_rejects_wrong_medium_for_same_material():
    # Regression (found in review, 2026-07-03): a query naming BOTH a material and a medium must not
    # backfill a reviewed card for the RIGHT material but the WRONG medium — e.g. "Ist FKM beständig
    # gegen Essigsäure?" must not ground on an FKM card scoped to amines/bases/ketones, not acids.
    pts = [
        _FakePoint(
            {
                "review_state": "draft",
                "card_id": f"draft-{idx}",
                "scope": {"material": ["FKM"], "medium": ["essigsäure"]},
            },
            1.0 - idx * 0.02,
        )
        for idx in range(5)
    ]
    wrong_medium = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-FKM-AMIN-LAUGE-KETON",
            "scope": {"material": ["FKM"], "medium": ["amine", "lauge", "keton"]},
        },
        0.80,
    )
    right_medium = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-FKM-SAEUREN",
            "scope": {"material": ["FKM"], "medium": ["essigsäure"]},
        },
        0.78,
    )

    selected = _select_points_with_reviewed_backfill(
        [*pts, wrong_medium],
        k=5,
        query="Ist FKM beständig gegen Essigsäure?",
    )
    assert wrong_medium not in selected  # material matches, medium doesn't → excluded

    selected_with_match = _select_points_with_reviewed_backfill(
        [*pts, wrong_medium, right_medium],
        k=5,
        query="Ist FKM beständig gegen Essigsäure?",
    )
    assert right_medium in selected_with_match  # material AND medium match → backfilled
    assert wrong_medium not in selected_with_match


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


# --- Hybrid retrieval (dense + sparse BM25, RRF-fused) + optional rerank — default OFF, see the
# settings docstrings for why (Qdrant collection schema migration, not a silent backfill). ---


class _ListLike(list):
    """Stand-in for numpy arrays: adds ``.tolist()`` (the only numpy method the retriever calls)."""

    def tolist(self):
        return list(self)


class _FakeDenseEmbedder:
    def embed(self, texts):
        return [_ListLike([0.1, 0.2, 0.3]) for _ in texts]


class _FakeSparseEmbedding:
    def __init__(self, indices, values):
        self.indices = _ListLike(indices)
        self.values = _ListLike(values)


class _FakeSparseEmbedder:
    def embed(self, texts):
        return [_FakeSparseEmbedding([1, 2], [0.5, 0.5]) for _ in texts]


class _FakeReranker:
    def __init__(self, score_map: dict[str, float]) -> None:
        self._score_map = score_map

    def rerank(self, query, documents):
        return [self._score_map.get(d, 0.0) for d in documents]


class _FakeQueryResult:
    def __init__(self, points) -> None:
        self.points = points


class _FakeClient:
    def __init__(self, points=None) -> None:
        self._points = points if points is not None else []
        self.last_query_points_kwargs: dict | None = None

    def query_points(self, collection, **kwargs):
        self.last_query_points_kwargs = kwargs
        return _FakeQueryResult(self._points)


def test_rerank_points_reorders_head_and_leaves_tail_untouched():
    pts = [
        _FakePoint({"claim_text": "low relevance", "card_id": "A"}, 0.9),
        _FakePoint({"claim_text": "high relevance", "card_id": "B"}, 0.8),
        _FakePoint({"claim_text": "untouched tail", "card_id": "C"}, 0.1),
    ]
    reranker = _FakeReranker({"low relevance": 0.1, "high relevance": 0.9})
    result = _rerank_points("query", pts, reranker, top_n=2)
    assert [p.payload["card_id"] for p in result] == ["B", "A", "C"]
    assert result[0].score == 0.9 and result[1].score == 0.1  # score replaced by rerank score


def test_rerank_points_noop_on_empty_or_zero_top_n():
    reranker = _FakeReranker({})
    assert _rerank_points("q", [], reranker, top_n=5) == []
    pts = [_FakePoint({"card_id": "A"}, 0.5)]
    assert _rerank_points("q", pts, reranker, top_n=0) == pts


class _FakeCreateClient:
    def __init__(self, exists: bool = False) -> None:
        self._exists = exists
        self.create_kwargs: dict | None = None

    def collection_exists(self, name):
        return self._exists

    def create_collection(self, name, **kwargs):
        self.create_kwargs = kwargs


def test_ensure_collection_creates_sparse_vector_when_requested():
    client = _FakeCreateClient(exists=False)
    ensure_collection(client, "col", 1536, sparse=True)
    assert client.create_kwargs["sparse_vectors_config"] is not None
    assert "sparse" in client.create_kwargs["sparse_vectors_config"]


def test_ensure_collection_dense_only_by_default():
    client = _FakeCreateClient(exists=False)
    ensure_collection(client, "col", 1536)
    assert client.create_kwargs["sparse_vectors_config"] is None


class _FakeVectorParams:
    def __init__(self, size: int) -> None:
        self.size = size


class _FakeCollectionParams:
    def __init__(self, dim: int, sparse_vectors=None) -> None:
        self.vectors = {"dense": _FakeVectorParams(dim)}
        self.sparse_vectors = sparse_vectors


class _FakeCollectionInfo:
    def __init__(self, dim: int, sparse_vectors=None) -> None:
        self.config = type("Cfg", (), {"params": _FakeCollectionParams(dim, sparse_vectors)})()


class _FakeExistingClient:
    def __init__(self, dim: int, sparse_vectors=None) -> None:
        self._info = _FakeCollectionInfo(dim, sparse_vectors)

    def collection_exists(self, name):
        return True

    def get_collection(self, name):
        return self._info


def test_ensure_collection_fails_fast_when_existing_lacks_sparse():
    client = _FakeExistingClient(1536, sparse_vectors=None)
    with pytest.raises(RuntimeError, match="sparse"):
        ensure_collection(client, "col", 1536, sparse=True)


def test_ensure_collection_passes_when_existing_has_sparse():
    client = _FakeExistingClient(1536, sparse_vectors={"sparse": object()})
    ensure_collection(client, "col", 1536, sparse=True)  # no raise


def test_ensure_collection_dense_check_unaffected_when_sparse_not_requested():
    client = _FakeExistingClient(1536, sparse_vectors=None)
    ensure_collection(client, "col", 1536, sparse=False)  # no raise — sparse not requested


def test_hybrid_and_rerank_helpers_not_constructed_when_disabled():
    # Both default OFF → no sparse embedder / reranker built, no import cost paid on the common path.
    r = QdrantFachkartenRetriever(Settings(), client=object(), embedder=object())
    assert r._sparse_embedder is None
    assert r._reranker is None


def test_retrieve_hybrid_builds_prefetch_with_dense_and_sparse_fused_by_rrf():
    from qdrant_client.models import Fusion, FusionQuery

    client = _FakeClient(points=[])
    r = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=True),
        client=client,
        embedder=_FakeDenseEmbedder(),
        sparse_embedder=_FakeSparseEmbedder(),
    )
    asyncio.run(r.retrieve("Informationen zu PTFE", tenant_id="eval", k=5))
    kwargs = client.last_query_points_kwargs
    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.RRF
    assert len(kwargs["prefetch"]) == 2
    assert {p.using for p in kwargs["prefetch"]} == {"dense", "sparse"}


def test_retrieve_dense_only_when_hybrid_disabled_no_prefetch():
    client = _FakeClient(points=[])
    r = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=False), client=client, embedder=_FakeDenseEmbedder()
    )
    asyncio.run(r.retrieve("Informationen zu PTFE", tenant_id="eval", k=5))
    kwargs = client.last_query_points_kwargs
    assert "prefetch" not in kwargs
    assert kwargs["using"] == "dense"  # unchanged dense-only path, byte-identical to pre-hybrid


def test_retrieve_applies_rerank_when_enabled():
    pts = [
        _FakePoint({"claim_text": "low", "card_id": "A", "review_state": "draft"}, 0.9),
        _FakePoint({"claim_text": "high", "card_id": "B", "review_state": "draft"}, 0.8),
    ]
    client = _FakeClient(points=pts)
    reranker = _FakeReranker({"low": 0.1, "high": 0.9})
    r = QdrantFachkartenRetriever(
        Settings(qdrant_rerank_enabled=True, qdrant_rerank_candidates=5),
        client=client,
        embedder=_FakeDenseEmbedder(),
        reranker=reranker,
    )
    res = asyncio.run(r.retrieve("q", tenant_id="eval", k=2))
    assert [f.card_id for f in res.provisional] == ["B", "A"]  # rerank order, not incoming score order


def test_retrieve_skips_rerank_when_disabled():
    pts = [
        _FakePoint({"claim_text": "low", "card_id": "A", "review_state": "draft"}, 0.9),
        _FakePoint({"claim_text": "high", "card_id": "B", "review_state": "draft"}, 0.8),
    ]
    client = _FakeClient(points=pts)
    r = QdrantFachkartenRetriever(
        Settings(qdrant_rerank_enabled=False), client=client, embedder=_FakeDenseEmbedder()
    )
    res = asyncio.run(r.retrieve("q", tenant_id="eval", k=2))
    assert [f.card_id for f in res.provisional] == ["A", "B"]  # incoming order preserved
