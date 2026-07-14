from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import RetrievalResult
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.qdrant_retrieval import (
    GLOBAL_TENANT,
    OpenAiEmbedder,
    QdrantFachkartenRetriever,
    _REVIEWED_BACKFILL_MIN_RELATIVE_SCORE_HYBRID,
    _hits_to_result,
    _make_embedder,
    _quelle,
    _rerank_points,
    _select_material_overview,
    _select_points_with_reviewed_backfill,
    claim_points,
    delete_card_points,
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
                "claim_id": "claim-epdm-definition",
                "sources": ["DIN 1234"],
                "claim_kind": "definition",
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
    assert gf.claim_kind == "definition"
    assert gf.claim_id == "claim-epdm-definition"
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


def test_reviewed_backfill_does_not_stop_after_a_single_reviewed_top_k_hit():
    top_reviewed = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "scope": {"material": ["PTFE"]},
        },
        0.96,
    )
    tail_reviewed_1 = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "scope": {"material": ["PTFE"]},
        },
        0.89,
    )
    tail_reviewed_2 = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "scope": {"material": ["PTFE"]},
        },
        0.87,
    )
    top = [
        _FakePoint({"review_state": "draft", "scope": {"material": ["PTFE"]}}, 1.0),
        top_reviewed,
    ]
    selected = _select_points_with_reviewed_backfill(
        [*top, tail_reviewed_1, tail_reviewed_2],
        k=2,
        query="Informationen zu PTFE",
    )

    assert selected[:2] == top
    assert selected[2:] == [tail_reviewed_1, tail_reviewed_2]


def test_reviewed_backfill_is_noop_once_reviewed_target_is_met():
    reviewed = [
        _FakePoint(
            {"review_state": "reviewed", "card_id": f"FK-{idx}"}, 0.9 - idx * 0.01
        )
        for idx in range(4)
    ]

    assert _select_points_with_reviewed_backfill(reviewed, k=3) == reviewed[:3]


def test_claim_points_one_per_claim_with_payload():
    cat = load_fachkarten()
    pts = list(claim_points(cat))
    assert len(pts) == sum(
        1 for card in cat.cards for claim in card.claims if not claim.quarantined
    )
    ids = set()
    required = {
        "card_id",
        "review_state",
        "claim_text",
        "claim_kind",
        "sources",
        "evidence",
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
    assert len(reviewed) == 79
    assert all(p["evidence"] for p in reviewed)
    assert (
        sum(
            any(
                item["source_type"] == "internal_domain_expert_attestation"
                for item in payload["evidence"]
            )
            for payload in reviewed
        )
        == 28
    )
    drafts = [p for _i, _t, p in pts if p["review_state"] == "draft"]
    assert drafts and all("vorläufig" in p["quelle"] for p in drafts)


def test_material_overview_selects_faceted_definition_strength_limit_and_qualification():
    scope = {"material": ["NBR"], "medium": [], "property": [], "application": []}

    def point(kind: str, text: str, score: float):
        return _FakePoint(
            {
                "review_state": "reviewed",
                "card_id": "FK-NBR-UEBERBLICK",
                "claim_kind": kind,
                "claim_text": text,
                "scope": scope,
            },
            score,
        )

    caution = point("safety_caution", "Grenze", 0.99)
    family_1 = point("family_tendency", "Staerke", 0.98)
    definition = point("definition", "Definition", 0.90)
    qualification = point("qualification_required", "Pruefung", 0.89)
    family_2 = point("family_tendency", "Trade-off", 0.88)
    selected = _select_material_overview(
        [caution, family_1, definition, qualification, family_2],
        5,
        "Hallo, bitte gib mir Details ueber NBR",
    )

    assert selected is not None
    assert [p.payload["claim_kind"] for p in selected] == [
        "definition",
        "family_tendency",
        "safety_caution",
        "qualification_required",
        "family_tendency",
    ]


def test_material_overview_policy_does_not_override_focused_property_query():
    points = [
        _FakePoint(
            {
                "review_state": "reviewed",
                "card_id": "FK-NBR-UEBERBLICK",
                "claim_kind": "definition",
                "scope": {
                    "material": ["NBR"],
                    "property": ["Ozonbestaendigkeit"],
                },
            },
            1.0,
        )
    ]

    assert _select_material_overview(points, 5, "Ozonbestaendigkeit von NBR") is None


def test_material_comparison_balances_parameter_evidence_across_subjects():
    def point(card_id: str, material: str, facets: list[str], score: float):
        return _FakePoint(
            {
                "review_state": "reviewed",
                "card_id": card_id,
                "claim_kind": "system_dependent",
                "answer_facets": facets,
                "scope": {"material": [material]},
            },
            score,
        )

    ptfe = [
        point("FK-PTFE-DEF", "PTFE", ["definition"], 0.99),
        point("FK-PTFE-VAR", "PTFE", ["variants"], 0.98),
        point("FK-PTFE-PROP", "PTFE", ["properties"], 0.97),
        point("FK-PTFE-TEMP", "PTFE", ["parameters"], 0.96),
        point("FK-PTFE-MEDIA", "PTFE", ["media_compatibility"], 0.95),
        point("FK-PTFE-OPS", "PTFE", ["operating_factors"], 0.94),
        point("FK-PTFE-LIMIT", "PTFE", ["limits"], 0.93),
        point("FK-PTFE-SELECT", "PTFE", ["selection_inputs"], 0.92),
    ]
    nbr = [
        point("FK-NBR-DEF", "NBR", ["definition"], 0.89),
        point("FK-NBR-VAR", "NBR", ["variants", "tradeoffs"], 0.88),
        point("FK-NBR-PROP", "NBR", ["properties", "media_compatibility"], 0.87),
        point(
            "FK-NBR-DAUERTEMP",
            "NBR",
            ["parameters", "limits", "failure_modes", "operating_factors"],
            0.86,
        ),
        point("FK-NBR-SELECT", "NBR", ["selection_inputs"], 0.85),
    ]
    selected = _select_material_overview(
        [*ptfe, *nbr],
        12,
        "Vergleiche NBR und PTFE: Temperatur, Medienverhalten und Grenzen.",
    )

    assert selected is not None
    selected_ids = {item.payload["card_id"] for item in selected}
    assert "FK-PTFE-TEMP" in selected_ids
    assert "FK-NBR-DAUERTEMP" in selected_ids


def test_seal_type_overview_does_not_pull_material_cards_that_only_name_an_application():
    seal_profile = [
        _FakePoint(
            {
                "review_state": "reviewed",
                "card_id": f"FK-ORING-{index}",
                "claim_kind": kind,
                "answer_facets": facets,
                "subject_type": "seal_type",
                "scope": {"application": ["O-Ring"]},
            },
            0.90 - index * 0.01,
        )
        for index, (kind, facets) in enumerate(
            [
                ("definition", ["definition", "mechanism"]),
                ("system_dependent", ["design_interfaces", "parameters"]),
                ("safety_caution", ["limits", "failure_modes"]),
            ]
        )
    ]
    material_mention = _FakePoint(
        {
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
            "claim_kind": "definition",
            "answer_facets": ["definition"],
            "subject_type": "material",
            "scope": {"material": ["PTFE"], "application": ["O-Ring"]},
        },
        0.99,
    )

    selected = _select_material_overview(
        [material_mention, *seal_profile], 5, "Erklaere einen O-Ring"
    )

    assert selected is not None
    assert all(point.payload["subject_type"] == "seal_type" for point in selected)


def test_retrieve_rejects_blank_tenant():
    # The mandatory-tenant guard fires BEFORE any qdrant import (so it is testable dep-free).
    r = QdrantFachkartenRetriever(Settings(), client=object(), embedder=object())
    raised = False
    try:
        asyncio.run(r.retrieve("frage", tenant_id="  "))
    except ValueError as e:
        raised = "tenant_id" in str(e)
    assert raised


def test_build_retriever_default_and_qdrant_prerequisite_guard():
    from sealai_v2.knowledge.retrieval import InProcessRetriever
    from sealai_v2.pipeline.pipeline import _build_retriever

    # default backend → in-process (no embedder load)
    assert isinstance(
        _build_retriever(Settings(retriever_backend="in_process")), InProcessRetriever
    )
    # An explicit production backend must not silently change retrieval semantics.
    with pytest.raises(RuntimeError, match="requires both Qdrant and Postgres"):
        _build_retriever(Settings(retriever_backend="qdrant", qdrant_url=None))


def test_build_retriever_fails_closed_on_construction_error(monkeypatch):
    # qdrant requested + endpoints set, but construction fails: refuse to start with a different
    # retriever than the one covered by release evidence.
    import sealai_v2.knowledge.qdrant_retrieval as qr
    from sealai_v2.pipeline.pipeline import _build_retriever

    def _boom(*a, **k):
        raise RuntimeError("simulated unavailable dep / unreachable qdrant")

    monkeypatch.setattr(qr, "QdrantFachkartenRetriever", _boom)
    with pytest.raises(RuntimeError, match="configured qdrant retriever is unavailable"):
        _build_retriever(
            Settings(
                retriever_backend="qdrant",
                qdrant_url="http://qdrant:6333",
                database_url="postgresql://test:test@postgres/test",
            )
        )


def test_build_retriever_rejects_unknown_backend():
    from sealai_v2.pipeline.pipeline import _build_retriever

    with pytest.raises(RuntimeError, match="unsupported retriever backend"):
        _build_retriever(Settings(retriever_backend="unexpected"))


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
    def __init__(self, points=None, profile_points=None) -> None:
        self._points = points if points is not None else []
        self._profile_points = profile_points if profile_points is not None else []
        self.last_query_points_kwargs: dict | None = None
        self.last_scroll_kwargs: dict | None = None

    def query_points(self, collection, **kwargs):
        self.last_query_points_kwargs = kwargs
        return _FakeQueryResult(self._points)

    def scroll(self, collection, **kwargs):
        self.last_scroll_kwargs = kwargs
        return self._profile_points, None


def test_rerank_points_reorders_head_and_leaves_tail_untouched():
    pts = [
        _FakePoint({"claim_text": "low relevance", "card_id": "A"}, 0.9),
        _FakePoint({"claim_text": "high relevance", "card_id": "B"}, 0.8),
        _FakePoint({"claim_text": "untouched tail", "card_id": "C"}, 0.1),
    ]
    reranker = _FakeReranker({"low relevance": 0.1, "high relevance": 0.9})
    result = _rerank_points("query", pts, reranker, top_n=2)
    assert [p.payload["card_id"] for p in result] == ["B", "A", "C"]
    assert (
        result[0].score == 0.9 and result[1].score == 0.1
    )  # score replaced by rerank score


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
        self.config = type(
            "Cfg", (), {"params": _FakeCollectionParams(dim, sparse_vectors)}
        )()


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
    ensure_collection(
        client, "col", 1536, sparse=False
    )  # no raise — sparse not requested


def test_direct_qdrant_ingest_is_rejected_when_postgres_is_configured():
    from sealai_v2.knowledge.qdrant_retrieval import ingest_fachkarten

    with pytest.raises(RuntimeError, match="direct Fachkarten-to-Qdrant"):
        ingest_fachkarten(Settings(database_url="sqlite://"))


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
        Settings(qdrant_hybrid_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )
    asyncio.run(r.retrieve("Informationen zu PTFE", tenant_id="eval", k=5))
    kwargs = client.last_query_points_kwargs
    assert "prefetch" not in kwargs
    assert (
        kwargs["using"] == "dense"
    )  # unchanged dense-only path, byte-identical to pre-hybrid


def test_retrieve_augments_semantic_results_with_exact_reviewed_subject_profile():
    semantic = [
        _FakePoint(
            {
                "claim_id": "definition",
                "claim_text": "PTFE definition",
                "card_id": "FK-PTFE-ENGINEERING-PROFILE",
                "review_state": "reviewed",
                "subject_type": "material",
                "answer_facets": ["definition"],
                "scope": {"material": ["PTFE"]},
            },
            0.9,
        )
    ]
    exact_profile_tail = _FakePoint(
        {
            "claim_id": "media",
            "claim_text": "PTFE filler and medium interaction",
            "card_id": "FK-PTFE-ENGINEERING-PROFILE",
            "review_state": "reviewed",
            "subject_type": "material",
            "answer_facets": ["media_compatibility"],
            "scope": {"material": ["PTFE"]},
        }
    )
    client = _FakeClient(points=semantic, profile_points=[exact_profile_tail])
    retriever = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )

    result = asyncio.run(
        retriever.retrieve("Technische Details zu PTFE", tenant_id="customer-a", k=12)
    )

    assert {fact.text for fact in result.grounding_facts} == {
        "PTFE definition",
        "PTFE filler and medium interaction",
    }
    assert client.last_scroll_kwargs is not None
    conditions = client.last_scroll_kwargs["scroll_filter"].must
    assert {condition.key for condition in conditions} == {
        "tenant_id",
        "review_state",
        "subject_type",
        "scope.material",
    }


def test_retrieve_balances_exact_profiles_for_both_comparison_subjects():
    def point(claim_id: str, material: str, facet: str, score: float = 0.0):
        return _FakePoint(
            {
                "claim_id": claim_id,
                "claim_text": f"{material} {facet}",
                "card_id": f"FK-{material}-PROFILE",
                "review_state": "reviewed",
                "subject_type": "material",
                "answer_facets": [facet],
                "scope": {"material": [material]},
            },
            score,
        )

    semantic = [point("ptfe-semantic", "PTFE", "definition", 0.9)]
    exact_profiles = [
        point("ptfe-parameters", "PTFE", "parameters"),
        point("nbr-definition", "NBR", "definition"),
        point("nbr-parameters", "NBR", "parameters"),
    ]
    client = _FakeClient(points=semantic, profile_points=exact_profiles)
    retriever = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )

    result = asyncio.run(
        retriever.retrieve("Vergleiche NBR und PTFE", tenant_id="customer-a", k=12)
    )

    card_ids = {fact.card_id for fact in result.grounding_facts}
    assert "FK-NBR-PROFILE" in card_ids
    assert "FK-PTFE-PROFILE" in card_ids
    scope_condition = next(
        condition
        for condition in client.last_scroll_kwargs["scroll_filter"].must
        if condition.key == "scope.material"
    )
    assert set(scope_condition.match.any) == {"NBR", "PTFE"}


def test_retrieve_does_not_scroll_material_profile_for_focused_case_question():
    client = _FakeClient(points=[])
    retriever = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )

    asyncio.run(
        retriever.retrieve(
            "PTFE bei 120 Grad und 8 bar auslegen", tenant_id="customer-a", k=5
        )
    )

    assert client.last_scroll_kwargs is None


def test_retrieve_scrolls_bounded_seal_profile_for_focused_rwdr_case():
    client = _FakeClient(points=[])
    retriever = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )

    asyncio.run(
        retriever.retrieve(
            "RWDR 45 mm bei 1500 U/min, Mineralöl und 80 Grad vorprüfen",
            tenant_id="customer-a",
            k=5,
        )
    )

    assert client.last_scroll_kwargs is not None
    scope_condition = next(
        condition
        for condition in client.last_scroll_kwargs["scroll_filter"].must
        if condition.key == "scope.application"
    )
    assert set(scope_condition.match.any) == {"RWDR"}


def test_retrieve_revalidates_qdrant_payload_against_postgres_ledger():
    pts = [
        _FakePoint(
            {
                "claim_id": "active",
                "claim_text": "stale text",
                "card_id": "STALE",
                "review_state": "reviewed",
            },
            0.9,
        ),
        _FakePoint(
            {
                "claim_id": "retired",
                "claim_text": "must disappear",
                "card_id": "RETIRED",
                "review_state": "reviewed",
            },
            0.8,
        ),
    ]

    class _Ledger:
        def resolve_claims(self, claim_ids, *, tenant_id):
            assert claim_ids == ("active", "retired") and tenant_id == "customer-a"
            return {
                "active": {
                    "claim_id": "active",
                    "claim_text": "canonical text",
                    "card_id": "FK-CANONICAL",
                    "review_state": "draft",
                    "sources": [],
                    "quelle": "ledger",
                    "scope": {},
                }
            }

    retriever = QdrantFachkartenRetriever(
        Settings(),
        client=_FakeClient(points=pts),
        embedder=_FakeDenseEmbedder(),
        knowledge_ledger=_Ledger(),
    )
    result = asyncio.run(retriever.retrieve("PTFE", tenant_id="customer-a", k=2))
    assert result.grounding_facts == ()
    assert [fact.text for fact in result.provisional] == ["canonical text"]


def test_retrieve_applies_rerank_when_enabled():
    pts = [
        _FakePoint({"claim_text": "low", "card_id": "A", "review_state": "draft"}, 0.9),
        _FakePoint(
            {"claim_text": "high", "card_id": "B", "review_state": "draft"}, 0.8
        ),
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
    assert [f.card_id for f in res.provisional] == [
        "B",
        "A",
    ]  # rerank order, not incoming score order


def test_retrieve_skips_rerank_when_disabled():
    pts = [
        _FakePoint({"claim_text": "low", "card_id": "A", "review_state": "draft"}, 0.9),
        _FakePoint(
            {"claim_text": "high", "card_id": "B", "review_state": "draft"}, 0.8
        ),
    ]
    client = _FakeClient(points=pts)
    r = QdrantFachkartenRetriever(
        Settings(qdrant_rerank_enabled=False),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )
    res = asyncio.run(r.retrieve("q", tenant_id="eval", k=2))
    assert [f.card_id for f in res.provisional] == [
        "A",
        "B",
    ]  # incoming order preserved


# --- Incident regression (2026-07-03): the reviewed-backfill's relative-score threshold is
# scale-dependent. Real numbers below are from the live incident (PTFE stopped grounding within
# minutes of the first hybrid-mode production deploy — the deploy was reverted same-day). ---


def _rrf_scale_candidates_with_deep_reviewed(reviewed_score: float = 0.0768):
    top5 = [
        _FakePoint(
            {
                "claim_text": f"draft {idx}",
                "review_state": "draft",
                "card_id": f"draft-{idx}",
            },
            score,
        )
        for idx, score in enumerate([0.5116, 0.5, 0.375, 0.3472, 0.3333])
    ]
    padding = [
        _FakePoint(
            {"claim_text": f"pad {i}", "review_state": "draft", "card_id": f"pad-{i}"},
            0.05,
        )
        for i in range(
            21
        )  # pushes the reviewed candidate well past a typical rerank-candidates window
    ]
    reviewed = _FakePoint(
        {
            "claim_text": "PTFE reviewed fact",
            "review_state": "reviewed",
            "card_id": "FK-PTFE-KALTFLUSS",
        },
        reviewed_score,
    )
    return [*top5, *padding, reviewed], reviewed


def test_reviewed_backfill_dense_ratio_is_too_strict_for_rrf_scale_scores():
    # Demonstrates the failure mode: the dense ratio (0.75) applied to RRF-scale scores silently
    # excludes a reviewed card that IS the correct backfill target — this is what broke PTFE grounding
    # under hybrid mode in production.
    candidates, reviewed = _rrf_scale_candidates_with_deep_reviewed()
    selected = _select_points_with_reviewed_backfill(
        candidates, k=5, query="PTFE", min_relative_score=0.75
    )
    assert reviewed not in selected


def test_reviewed_backfill_hybrid_ratio_finds_the_same_rrf_scale_candidate():
    # The fix: a ratio calibrated against RRF's own (much steeper) decay finds the identical candidate
    # the dense ratio missed above — same input, only the ratio differs.
    candidates, reviewed = _rrf_scale_candidates_with_deep_reviewed()
    selected = _select_points_with_reviewed_backfill(
        candidates,
        k=5,
        query="PTFE",
        min_relative_score=_REVIEWED_BACKFILL_MIN_RELATIVE_SCORE_HYBRID,
    )
    assert reviewed in selected


def test_retrieve_hybrid_with_rerank_still_grounds_deep_reviewed_candidate():
    # End-to-end regression test through the full retrieve() call with BOTH hybrid and rerank enabled
    # together (the exact incident configuration) — proves backfill selection runs on the RRF-native
    # score scale before rerank ever touches the candidates, and that grounding survives intact.
    candidates, _reviewed = _rrf_scale_candidates_with_deep_reviewed()
    client = _FakeClient(points=candidates)
    reranker = _FakeReranker({f"draft {i}": 0.5 - i * 0.01 for i in range(5)})
    r = QdrantFachkartenRetriever(
        Settings(
            qdrant_hybrid_enabled=True,
            qdrant_rerank_enabled=True,
            qdrant_rerank_candidates=20,
        ),
        client=client,
        embedder=_FakeDenseEmbedder(),
        sparse_embedder=_FakeSparseEmbedder(),
        reranker=reranker,
    )
    res = asyncio.run(r.retrieve("Informationen zu PTFE", tenant_id="eval", k=5))
    assert res.grounded
    assert [f.card_id for f in res.grounding_facts] == ["FK-PTFE-KALTFLUSS"]


class _FakeCountResult:
    def __init__(self, count: int) -> None:
        self.count = count


class _FakeDeleteClient:
    """Tracks what filter delete_card_points builds and whether .delete() was actually called —
    a card_id with zero matching points must be a no-op (never call delete for nothing)."""

    def __init__(self, matching_count: int) -> None:
        self._matching_count = matching_count
        self.count_calls: list[tuple[str, object]] = []
        self.delete_calls: list[tuple[str, object]] = []

    def count(self, collection, count_filter=None):
        self.count_calls.append((collection, count_filter))
        return _FakeCountResult(self._matching_count)

    def delete(self, collection, points_selector=None):
        self.delete_calls.append((collection, points_selector))


def test_delete_card_points_filters_by_card_id_and_returns_the_prior_count():
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = _FakeDeleteClient(matching_count=3)
    deleted = delete_card_points(client, "col", "FK-DRAFT-DOC-42")
    assert deleted == 3
    assert len(client.delete_calls) == 1
    _, flt = client.delete_calls[0]
    assert flt == Filter(
        must=[FieldCondition(key="card_id", match=MatchValue(value="FK-DRAFT-DOC-42"))]
    )


def test_delete_card_points_is_a_noop_when_nothing_matches():
    client = _FakeDeleteClient(matching_count=0)
    deleted = delete_card_points(client, "col", "FK-NEVER-INGESTED")
    assert deleted == 0
    assert client.delete_calls == []  # never called — nothing to delete


class _FailingEmbedder:
    """Simulates every retry the OpenAI SDK already attempts having been exhausted (or a
    non-retryable error, e.g. an invalid key) — always raises."""

    def embed(self, texts):
        raise RuntimeError("simulated OpenAI outage — all SDK-level retries exhausted")


def test_retrieve_degrades_to_an_empty_result_on_an_embed_failure_never_raises():
    # 2026-07-04 RAG audit: a transient (or persistent) embedding failure during an actual
    # retrieve() call — as opposed to at retriever CONSTRUCTION time, which _build_retriever
    # (pipeline.py) already covers — must degrade this ONE turn to "nothing grounded", not crash it.
    r = QdrantFachkartenRetriever(
        Settings(), client=_FakeClient(points=[]), embedder=_FailingEmbedder()
    )
    res = asyncio.run(r.retrieve("Informationen zu PTFE", tenant_id="eval", k=5))
    assert res == RetrievalResult()
    assert res.grounded is False


def test_retrieve_still_works_normally_when_the_embedder_does_not_fail():
    # guard against the fail-safe wrapper accidentally swallowing a SUCCESSFUL retrieval too
    pts = [
        _FakePoint({"claim_text": "x", "card_id": "A", "review_state": "draft"}, 0.9)
    ]
    r = QdrantFachkartenRetriever(
        Settings(), client=_FakeClient(points=pts), embedder=_FakeDenseEmbedder()
    )
    res = asyncio.run(r.retrieve("q", tenant_id="eval", k=5))
    assert len(res.provisional) == 1
