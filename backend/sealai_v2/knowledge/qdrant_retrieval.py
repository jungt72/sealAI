"""L2 PRODUCTION retrieval — semantic Fachkarten search over Qdrant (build-spec §3 deferred path).

Behind the SAME ``Retriever`` Protocol as the in-process keyword matcher (``knowledge/retrieval.py``),
so swapping it in is pure config (``SEALAI_V2_RETRIEVER_BACKEND=qdrant``). The in-process retriever
stays the deterministic CI/eval MEASUREMENT instrument; THIS is the production recall path.

Embedding: PROD = OpenAI ``text-embedding-3-small`` (dense, 1536-dim, RAM-safe — no local model; DATA
leaves the box for the API embed call). Pluggable via ``embed_provider`` — ``fastembed`` e5-large is the
optional OFFLINE alternative (it needs the ``query:``/``passage:`` prefix; openai uses ""). Doctrine holds:
tenant scope is a mandatory server-side filter; **reviewed** claims → ``grounding_facts`` (authoritative),
**draft** claims → ``provisional`` ("vorläufig"), split by the per-CLAIM ``review_state`` in the payload.

``fastembed``/``qdrant-client`` are imported LAZILY so this module imports cleanly in the hermetic
offline env that lacks them (they are only needed when the qdrant backend is actually constructed —
the production image). Client + embedder are injectable for tests; the payload→facts mapping is a
pure function (``_hits_to_result``) with no optional-dep import, so the doctrine logic is unit-tested
without fastembed/qdrant installed.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sealai_v2.core.contracts import GroundingFact, RetrievalResult
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, load_fachkarten

if TYPE_CHECKING:
    from sealai_v2.config.settings import Settings

_log = logging.getLogger("sealai_v2.knowledge.qdrant_retrieval")

GLOBAL_TENANT = (
    "sealai"  # seed Fachkarten are GLOBAL knowledge (mirrors V1's shared tenant)
)
_DENSE = "dense"
_SPARSE = "sparse"
_POINT_NAMESPACE = uuid.UUID(
    "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
)  # uuid5 NAMESPACE_URL
_REVIEWED_BACKFILL_FACTOR = 24
_REVIEWED_BACKFILL_MAX_CANDIDATES = 128
_REVIEWED_BACKFILL_MAX_FACTS = 2
# Incident note (2026-07-03): this ratio is SCALE-DEPENDENT — it only makes sense relative to the
# score distribution it was calibrated against. Dense cosine similarity decays gently across rank
# (e.g. top=0.69, rank~68/128=0.58 — still 84% of top), so 0.75 lets a genuinely-relevant reviewed
# card several dozen ranks deep still qualify. Qdrant's RRF fusion decays MUCH more steeply (e.g.
# top=0.51, the equivalent genuinely-relevant reviewed card at rank~27/128=0.077 — only 15% of top);
# reusing the dense ratio for RRF-fused scores made the gate impossibly strict and silently defeated
# the whole reviewed-backfill mechanism under hybrid mode (caught live: PTFE stopped grounding within
# minutes of the first hybrid-mode production deploy, reverted same-day). Each retrieval mode needs
# its OWN ratio, chosen against that mode's OWN score distribution — see qdrant_hybrid_enabled callers.
_REVIEWED_BACKFILL_MIN_RELATIVE_SCORE = 0.75
_REVIEWED_BACKFILL_MIN_RELATIVE_SCORE_HYBRID = 0.10


def _query_text(q: str, prefix: str = "query: ") -> str:
    # e5 needs the "query:"/"passage:" asymmetry; OpenAI/jina/MiniLM use "" (raw text). Prefix is config.
    return f"{prefix}{q}"


def _passage_text(t: str, prefix: str = "passage: ") -> str:
    return f"{prefix}{t}"


def _quelle(card_id: str, provenance: tuple[str, ...], *, reviewed: bool) -> str:
    # Byte-identical to ``knowledge/retrieval.py::_quelle`` so the qdrant adapter's citations match the
    # in-process ones for the same card.
    tag = "reviewed" if reviewed else "draft — vorläufig, gegen Hersteller verifizieren"
    return f"Fachkarte {card_id} ({tag}; {', '.join(provenance)})"


def _hits_to_result(points) -> RetrievalResult:
    """PURE (no qdrant/fastembed import): split scored points into reviewed (grounding_facts,
    authoritative) vs draft (provisional, "vorläufig") by the per-claim ``review_state`` payload.
    This is the doctrine-critical mapping — unit-tested without the optional deps installed."""
    reviewed: list[GroundingFact] = []
    provisional: list[GroundingFact] = []
    for point in points:
        p = getattr(point, "payload", None) or {}
        fact = GroundingFact(
            text=p.get("claim_text", ""),
            quelle=p.get("quelle", ""),
            card_id=p.get("card_id", ""),
            sources=tuple(p.get("sources", ())),
            kind="card",
        )
        bucket = reviewed if p.get("review_state") == "reviewed" else provisional
        bucket.append(fact)
    return RetrievalResult(
        grounding_facts=tuple(reviewed), provisional=tuple(provisional)
    )


def _review_state(point) -> str:
    return (getattr(point, "payload", None) or {}).get("review_state", "")


def _score(point) -> float | None:
    value = getattr(point, "score", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payload(point) -> dict:
    return getattr(point, "payload", None) or {}


def _scope_dim(point, dim: str) -> tuple[str, ...]:
    scope = _payload(point).get("scope", {}) or {}
    return tuple(str(item) for item in scope.get(dim, ()))


def _detected_scope_tokens(points, query: str, dim: str) -> set[str]:
    """Scope tags (from ANY candidate's ``scope[dim]``) that actually appear in the query — word-
    boundary matched via the SAME shared tokenizer the §4 matrix and the L3 trap gate already use
    (``core.text_match``), not a raw substring check (which over-matches on short/compound German
    tokens, e.g. a bare "öl" tag inside "Kühlöl"). A dimension with zero detected tokens is treated
    as unconstrained by the query — callers must not filter on it (see ``_point_matches_scope``)."""
    q_tokens = query_tokens(query or "")
    q_norm = (query or "").lower()
    if not q_tokens:
        return set()
    tags: set[str] = set()
    for point in points:
        for tag in _scope_dim(point, dim):
            if tag and tag_matches(tag, q_tokens, q_norm):
                tags.add(tag.lower())
    return tags


def _card_id_matches_material(point, material_tokens: set[str]) -> bool:
    card_id = str(_payload(point).get("card_id", "")).lower()
    return any(tok in card_id for tok in material_tokens)


def _point_matches_scope(point, dim: str, tokens: set[str]) -> bool:
    """True when ``tokens`` is empty (the query didn't name anything on this dimension — not a
    constraint) OR the point's own ``scope[dim]`` overlaps with the detected tokens."""
    if not tokens:
        return True
    point_tags = {t.lower() for t in _scope_dim(point, dim)}
    return bool(tokens & point_tags)


def _matches_material_scope(point, material_tokens: set[str]) -> bool:
    return _point_matches_scope(
        point, "material", material_tokens
    ) or _card_id_matches_material(point, material_tokens)


class _ScoredPoint:
    """Minimal (payload, score) carrier matching ``ScoredPoint``'s ``.payload``/``.score`` duck-type —
    used to substitute the qdrant-native score with the cross-encoder's score after ``_rerank_points``,
    so every downstream helper (``_score``, ``_select_points_with_reviewed_backfill``) stays agnostic to
    whether a point came straight from qdrant or was reordered by the reranker."""

    __slots__ = ("payload", "score")

    def __init__(self, payload: dict, score: float) -> None:
        self.payload = payload
        self.score = score


def _rerank_points(query: str, points, reranker, top_n: int):
    """Cross-encoder rerank the top ``top_n`` candidates (by incoming rank) against the query; the rest
    pass through untouched — reranking cost is O(top_n) forward passes, not O(all candidates), see the
    ``qdrant_rerank_candidates`` setting docstring. PURE aside from the injected ``reranker`` (duck-typed:
    ``.rerank(query, documents) -> Iterable[float]``, fastembed's ``TextCrossEncoder`` protocol), so this
    is unit-testable with a fake reranker and no fastembed import."""
    if not points or top_n <= 0:
        return points
    head, tail = list(points[:top_n]), list(points[top_n:])
    docs = [_payload(p).get("claim_text", "") for p in head]
    scores = list(reranker.rerank(query, docs))
    reordered = [
        _ScoredPoint(_payload(p), float(s))
        for s, p in sorted(zip(scores, head), key=lambda sp: -sp[0])
    ]
    return reordered + tail


def _select_points_with_reviewed_backfill(
    points,
    k: int,
    query: str = "",
    *,
    min_relative_score: float = _REVIEWED_BACKFILL_MIN_RELATIVE_SCORE,
):
    """Return the normal top-k, plus a tiny reviewed backfill when top-k is draft-only.

    Production Qdrant stores many draft points for broad material topics. A general query such as
    "Informationen zu PTFE" can therefore rank relevant but unreviewed overview claims above the few
    reviewed safety/caveat cards. The output contract treats only reviewed claims as grounding_facts,
    so a draft-only top-k makes the turn falsely ungrounded even though reviewed knowledge exists just
    below the cutoff. Keep the original top-k intact, then add a small, score-bounded reviewed tail.

    ``min_relative_score`` is SCALE-DEPENDENT (see the constant's docstring) — callers on a non-dense
    score scale (RRF fusion) MUST pass the matching mode-specific ratio, not the dense default.
    """
    limit = max(0, k)
    candidates = list(points)
    selected = candidates[:limit]
    if (
        limit == 0
        or not candidates
        or any(_review_state(p) == "reviewed" for p in selected)
    ):
        return selected

    top_score = _score(candidates[0])
    min_score = top_score * min_relative_score if top_score is not None else None
    material_tokens = _detected_scope_tokens(candidates, query, "material")
    # Medium check (fixes a real cross-contamination case found in review, 2026-07-03): a query
    # naming BOTH a material and a medium ("Ist FKM beständig gegen Essigsäure?") must not backfill
    # a reviewed card for the RIGHT material but the WRONG medium (e.g. an FKM×Lauge card for an
    # FKM×Essigsäure question) — material overlap alone is not "on topic". When the query names no
    # recognisable medium at all (e.g. the PTFE property-only case this backfill was built for),
    # medium_tokens is empty and _point_matches_scope treats the dimension as unconstrained.
    medium_tokens = _detected_scope_tokens(candidates, query, "medium")
    eligible = []
    for idx, point in enumerate(candidates[limit:]):
        if _review_state(point) != "reviewed":
            continue
        if material_tokens and not _matches_material_scope(point, material_tokens):
            continue
        if not _point_matches_scope(point, "medium", medium_tokens):
            continue
        point_score = _score(point)
        if (
            min_score is not None
            and point_score is not None
            and point_score < min_score
        ):
            continue
        eligible.append((idx, point))

    if material_tokens and any(
        _card_id_matches_material(p, material_tokens) for _idx, p in eligible
    ):
        eligible = [
            (idx, p)
            for idx, p in eligible
            if _card_id_matches_material(p, material_tokens)
        ]

    for _idx, point in eligible[:_REVIEWED_BACKFILL_MAX_FACTS]:
        selected.append(point)
    return selected


def claim_points(catalog: FachkartenCatalog):
    """Yield ``(point_id, passage_text, payload)`` per CLAIM — the embed unit. ``review_state`` is
    per-claim (a card mixes reviewed + draft); the retriever splits the result channels on it.
    PURE (no optional-dep import) so it is unit-tested directly."""
    for card in catalog.cards:
        for idx, claim in enumerate(card.claims):
            pid = str(
                uuid.uuid5(_POINT_NAMESPACE, f"{card.id}:{idx}")
            )  # idempotent upsert key
            payload = {
                "card_id": card.id,
                "review_state": claim.review_state,
                "claim_text": claim.text,
                "sources": list(claim.sources),
                "provenance": list(card.provenance),
                "scope": {k: list(v) for k, v in card.scope.items()},
                "tenant_id": GLOBAL_TENANT,
                "version": card.version,
                "quelle": _quelle(card.id, card.provenance, reviewed=claim.reviewed),
            }
            yield (
                pid,
                claim.text,
                payload,
            )  # raw; the passage prefix is applied at embed time


class OpenAiEmbedder:
    """API embeddings (OpenAI text-embedding-3) — NO local model → NO RAM/OOM (the e5-large failure that
    took chat down), strong on German, reuses the existing OPENAI_API_KEY. Drop-in for FastEmbed's
    ``embed``: returns numpy arrays (the retriever/ingestor call ``.tolist()`` on each)."""

    def __init__(
        self, model: str, *, api_key: str, base_url: str | None = None
    ) -> None:
        from openai import OpenAI  # lazy

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, texts):
        import numpy as np  # lazy

        items = list(texts)
        if not items:
            return []
        resp = self._client.embeddings.create(model=self._model, input=items)
        return [np.array(d.embedding) for d in resp.data]


def _make_embedder(settings: "Settings"):
    if (
        getattr(settings, "embed_provider", "fastembed") or "fastembed"
    ).lower() == "openai":
        import os

        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "embed_provider=openai but no OPENAI_API_KEY in the environment"
            )
        return OpenAiEmbedder(
            settings.embed_model, api_key=key, base_url=os.getenv("OPENAI_BASE_URL")
        )
    from fastembed import (
        TextEmbedding,
    )  # lazy: optional dep, present only in the production image

    return TextEmbedding(
        model_name=settings.embed_model, cache_dir=settings.embed_cache_dir
    )


def _make_sparse_embedder(settings: "Settings"):
    """BM25 sparse embedder (fastembed's bundled ``Qdrant/bm25`` model) — real term-frequency scoring
    with German stopwords, NOT a second neural model. Only constructed when hybrid retrieval is
    actually enabled (lazy import: fastembed sparse support ships in the same optional dep as dense)."""
    from fastembed import SparseTextEmbedding  # lazy

    return SparseTextEmbedding(
        model_name=settings.qdrant_sparse_model, language="german"
    )


def _make_reranker(settings: "Settings"):
    """Cross-encoder reranker (fastembed's bundled multilingual model) — a discriminative relevance
    scorer, not a generative LLM (Leitsatz L1: the LLM only formulates the final answer)."""
    from fastembed.rerank.cross_encoder import TextCrossEncoder  # lazy

    return TextCrossEncoder(model_name=settings.qdrant_rerank_model)


def _make_client(settings: "Settings"):
    from qdrant_client import QdrantClient  # lazy

    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def _embed_dim(embedder) -> int:
    return len(next(iter(embedder.embed(["passage: _warmup_"]))).tolist())


def ensure_collection(
    client, collection: str, dim: int, *, sparse: bool = False
) -> None:
    """Idempotent: create the collection (named ``dense`` vector, COSINE) if absent; if present,
    FAIL-FAST on a dimension mismatch (mirrors V1's qdrant_bootstrap guard — a silent re-embed at a
    wrong dim is a data-corruption trap). ``sparse=True`` additionally declares a named ``sparse``
    vector (IDF-modified, for BM25 — see the hybrid-retrieval settings docstring) at creation time.
    Qdrant collections fix their vector schema at creation, so adding sparse to an EXISTING dense-only
    collection needs a recreate + re-ingest — this function does not do that migration silently; it
    only fails fast if the existing collection doesn't already have what's requested."""
    from qdrant_client.models import (  # lazy
        Distance,
        Modifier,
        SparseVectorParams,
        VectorParams,
    )

    if client.collection_exists(collection):
        info = client.get_collection(collection)
        existing = info.config.params.vectors[_DENSE].size
        if existing != dim:
            raise RuntimeError(
                f"Qdrant collection {collection!r} has dim {existing}, embedder needs {dim} — refuse"
            )
        if sparse and not (info.config.params.sparse_vectors or {}).get(_SPARSE):
            raise RuntimeError(
                f"Qdrant collection {collection!r} has no {_SPARSE!r} vector — hybrid retrieval needs a "
                "collection recreate + full re-ingest (owner-authorized migration, not automatic)"
            )
        return
    client.create_collection(
        collection,
        vectors_config={_DENSE: VectorParams(size=dim, distance=Distance.COSINE)},
        sparse_vectors_config=(
            {_SPARSE: SparseVectorParams(modifier=Modifier.IDF)} if sparse else None
        ),
    )


def ingest_fachkarten(
    settings, *, client=None, embedder=None, catalog=None, sparse_embedder=None
) -> int:
    """Eval-only scratch-index loader. Production writes are rejected when a DB is configured.

    Embed every Fachkarten claim (``passage:``) + upsert into Qdrant. Idempotent (uuid5 point ids
    → re-seed overwrites; a claim flipping draft→reviewed updates in place). Returns #points upserted.
    When ``settings.qdrant_hybrid_enabled``, also embeds + upserts a ``sparse`` (BM25) vector alongside
    ``dense`` — the collection must already have both vectors declared (``ensure_collection(...,
    sparse=True)``, called below with the same flag)."""
    if getattr(settings, "database_url", None):
        raise RuntimeError(
            "direct Fachkarten-to-Qdrant writes are disabled when Postgres is configured; "
            "write the knowledge ledger and drain its outbox"
        )

    from qdrant_client.models import PointStruct, SparseVector  # lazy

    client = client or _make_client(settings)
    embedder = embedder or _make_embedder(settings)
    catalog = catalog or load_fachkarten()
    hybrid = bool(getattr(settings, "qdrant_hybrid_enabled", False))
    ensure_collection(
        client, settings.qdrant_collection, _embed_dim(embedder), sparse=hybrid
    )
    items = list(claim_points(catalog))
    if not items:
        return 0
    pprefix = getattr(settings, "embed_passage_prefix", "passage: ")
    passages = [_passage_text(txt, pprefix) for _pid, txt, _p in items]
    vectors = [v.tolist() for v in embedder.embed(passages)]

    sparse_vectors = None
    if hybrid:
        sparse_embedder = sparse_embedder or _make_sparse_embedder(settings)
        raw_texts = [
            txt for _pid, txt, _p in items
        ]  # BM25 has no passage/query asymmetry
        sparse_vectors = [
            SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in sparse_embedder.embed(raw_texts)
        ]

    points = []
    for idx, ((pid, _txt, payload), vec) in enumerate(zip(items, vectors)):
        vector = {_DENSE: vec}
        if sparse_vectors is not None:
            vector[_SPARSE] = sparse_vectors[idx]
        points.append(PointStruct(id=pid, vector=vector, payload=payload))
    client.upsert(settings.qdrant_collection, points=points)
    return len(points)


def delete_card_points(client, collection: str, card_id: str) -> int:
    """Legacy/eval cleanup helper; production retirement belongs to the knowledge ledger.

    Delete every point whose payload ``card_id`` matches, via a Qdrant filter rather than
    recomputing legacy point IDs. Returns the pre-delete point count; deleting
    zero matching points (card_id not present) is a safe no-op, not an error."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(must=[FieldCondition(key="card_id", match=MatchValue(value=card_id))])
    before = client.count(collection, count_filter=flt).count
    if before:
        client.delete(collection, points_selector=flt)
    return before


class QdrantFachkartenRetriever:
    """``Retriever`` Protocol impl — semantic Fachkarten recall over Qdrant. Drop-in for
    ``InProcessRetriever``: same async signature, same mandatory tenant, same RetrievalResult shape."""

    def __init__(
        self,
        settings,
        *,
        client=None,
        embedder=None,
        sparse_embedder=None,
        reranker=None,
        knowledge_ledger=None,
    ) -> None:
        self._collection = settings.qdrant_collection
        self._client = client or _make_client(settings)
        self._embedder = embedder or _make_embedder(settings)
        self._qprefix = getattr(settings, "embed_query_prefix", "query: ")
        # Hybrid retrieval (dense+sparse BM25, RRF-fused) + optional cross-encoder rerank — both default
        # OFF (see settings docstring: flipping qdrant_hybrid_enabled needs a collection migration).
        # Sparse embedder / reranker are constructed lazily (only when actually enabled) so the common
        # dense-only path never pays their import/model-load cost.
        self._hybrid_enabled = bool(getattr(settings, "qdrant_hybrid_enabled", False))
        self._hybrid_candidate_limit = int(
            getattr(settings, "qdrant_hybrid_candidate_limit", 128)
        )
        self._sparse_embedder = sparse_embedder or (
            _make_sparse_embedder(settings) if self._hybrid_enabled else None
        )
        self._rerank_enabled = bool(getattr(settings, "qdrant_rerank_enabled", False))
        self._rerank_candidates = int(getattr(settings, "qdrant_rerank_candidates", 20))
        self._reranker = reranker or (
            _make_reranker(settings) if self._rerank_enabled else None
        )
        # Production injects the Postgres ledger. Keeping this optional preserves
        # the pure Qdrant adapter as a hermetic retrieval-quality instrument, but
        # ``pipeline._build_retriever`` never enables Qdrant in production without it.
        self._knowledge_ledger = knowledge_ledger

    async def retrieve(
        self, query: str, *, tenant_id: str, k: int = 5
    ) -> RetrievalResult:
        if not (tenant_id or "").strip():
            raise ValueError("tenant_id is mandatory (P0 repository-layer scope)")
        import asyncio

        # FastEmbed (local ONNX) + the qdrant call are sync/CPU+IO → off the event loop in a thread.
        try:
            return await asyncio.to_thread(self._retrieve_sync, query, tenant_id, k)
        except Exception as exc:  # noqa: BLE001 — fail safe to an empty result; never crash the turn
            # 2026-07-04 RAG audit: the OpenAI SDK already retries transient embed failures itself
            # (DEFAULT_MAX_RETRIES=2 with backoff) — this catches what's left AFTER those are
            # exhausted, or a non-retryable error (bad key, unreachable Qdrant mid-turn). Degrades
            # this ONE turn to "nothing grounded", the exact same shape as any other query with no
            # matching Fachkarte (the pipeline already handles that case correctly) — never a 500.
            # _build_retriever's own fail-safe (pipeline.py) only covers a failure at STARTUP
            # (constructing the retriever); this is the missing counterpart for an already-built one.
            _log.warning(
                "qdrant retrieve failed (%s) → empty result for this turn, not a crash",
                exc,
            )
            return RetrievalResult()

    def _retrieve_sync(self, query: str, tenant_id: str, k: int) -> RetrievalResult:
        from qdrant_client.models import FieldCondition, Filter, MatchAny  # lazy

        tenant_filter = Filter(
            must=[
                FieldCondition(
                    key="tenant_id", match=MatchAny(any=[tenant_id, GLOBAL_TENANT])
                )
            ]
        )
        requested_limit = max(0, k)
        candidate_limit = min(
            _REVIEWED_BACKFILL_MAX_CANDIDATES,
            max(requested_limit, requested_limit * _REVIEWED_BACKFILL_FACTOR),
        )

        if self._hybrid_enabled:
            points = self._query_hybrid(query, tenant_filter, candidate_limit)
            # RRF-fused scores decay far more steeply than dense cosine similarity — the SAME relative
            # threshold silently starves the backfill under hybrid mode (see the constant's docstring
            # for the incident this caught). Each score scale needs its own calibrated ratio.
            min_relative_score = _REVIEWED_BACKFILL_MIN_RELATIVE_SCORE_HYBRID
        else:
            qvec = next(
                iter(self._embedder.embed([_query_text(query, self._qprefix)]))
            ).tolist()
            res = self._client.query_points(
                self._collection,
                query=qvec,
                using=_DENSE,
                limit=candidate_limit,
                query_filter=tenant_filter,
                with_payload=True,
            )
            points = res.points
            min_relative_score = _REVIEWED_BACKFILL_MIN_RELATIVE_SCORE

        if self._knowledge_ledger is not None:
            claim_ids = tuple(
                str(_payload(point).get("claim_id") or "") for point in points
            )
            canonical = self._knowledge_ledger.resolve_claims(
                claim_ids, tenant_id=tenant_id
            )
            # Drop legacy, retired and rejected index entries. Every payload field
            # used below comes from Postgres, while Qdrant contributes only score/order.
            points = [
                _ScoredPoint(canonical[claim_id], _score(point) or 0.0)
                for point, claim_id in zip(points, claim_ids)
                if claim_id in canonical
            ]

        # Backfill selection MUST run on the retrieval-native score scale (dense or RRF, whichever the
        # branch above produced) BEFORE any reranking — the cross-encoder only rescores its own top-N
        # slice, leaving the untouched tail on the old scale, so comparing a post-rerank top_score
        # against a pre-rerank tail score would silently mix two incompatible scales (same incident).
        selected = _select_points_with_reviewed_backfill(
            points, k, query, min_relative_score=min_relative_score
        )

        # Rerank is a pure ORDERING refinement over the already-selected small set (top-k + backfill,
        # never more than k + _REVIEWED_BACKFILL_MAX_FACTS), not a pre-filter over the wide candidate
        # pool — keeps it cheap and keeps its score scale fully isolated from backfill selection.
        if self._rerank_enabled and selected:
            selected = _rerank_points(
                query,
                selected,
                self._reranker,
                min(len(selected), self._rerank_candidates),
            )

        return _hits_to_result(selected)

    def _query_hybrid(self, query: str, tenant_filter, candidate_limit: int):
        """Dense + sparse (BM25) prefetch, fused server-side via Qdrant's native RRF — deterministic,
        no model involved in the fusion step itself (only in producing each candidate list)."""
        from qdrant_client.models import (  # lazy
            Fusion,
            FusionQuery,
            Prefetch,
            SparseVector,
        )

        limit = max(candidate_limit, self._hybrid_candidate_limit)
        qvec = next(
            iter(self._embedder.embed([_query_text(query, self._qprefix)]))
        ).tolist()
        sparse = next(iter(self._sparse_embedder.embed([query])))
        sparse_query = SparseVector(
            indices=sparse.indices.tolist(), values=sparse.values.tolist()
        )
        res = self._client.query_points(
            self._collection,
            prefetch=[
                Prefetch(query=qvec, using=_DENSE, limit=limit, filter=tenant_filter),
                Prefetch(
                    query=sparse_query,
                    using=_SPARSE,
                    limit=limit,
                    filter=tenant_filter,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            query_filter=tenant_filter,
            with_payload=True,
        )
        return res.points
