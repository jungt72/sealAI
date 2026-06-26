"""L2 PRODUCTION retrieval — semantic Fachkarten search over Qdrant (build-spec §3 deferred path).

Behind the SAME ``Retriever`` Protocol as the in-process keyword matcher (``knowledge/retrieval.py``),
so swapping it in is pure config (``SEALAI_V2_RETRIEVER_BACKEND=qdrant``). The in-process retriever
stays the deterministic CI/eval MEASUREMENT instrument; THIS is the production recall path.

Embedding: local FastEmbed ``multilingual-e5-large`` (dense, no API — nothing leaves the box; strong
on German). e5 requires the ``query:``/``passage:`` prefix convention (applied here). Doctrine holds:
tenant scope is a mandatory server-side filter; **reviewed** claims → ``grounding_facts`` (authoritative),
**draft** claims → ``provisional`` ("vorläufig"), split by the per-CLAIM ``review_state`` in the payload.

``fastembed``/``qdrant-client`` are imported LAZILY so this module imports cleanly in the hermetic
offline env that lacks them (they are only needed when the qdrant backend is actually constructed —
the production image). Client + embedder are injectable for tests; the payload→facts mapping is a
pure function (``_hits_to_result``) with no optional-dep import, so the doctrine logic is unit-tested
without fastembed/qdrant installed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sealai_v2.core.contracts import GroundingFact, RetrievalResult
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, load_fachkarten

if TYPE_CHECKING:
    from sealai_v2.config.settings import Settings

GLOBAL_TENANT = (
    "sealai"  # seed Fachkarten are GLOBAL knowledge (mirrors V1's shared tenant)
)
_DENSE = "dense"
_POINT_NAMESPACE = uuid.UUID(
    "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
)  # uuid5 NAMESPACE_URL


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


def _make_client(settings: "Settings"):
    from qdrant_client import QdrantClient  # lazy

    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def _embed_dim(embedder) -> int:
    return len(next(iter(embedder.embed(["passage: _warmup_"]))).tolist())


def ensure_collection(client, collection: str, dim: int) -> None:
    """Idempotent: create the collection (named ``dense`` vector, COSINE) if absent; if present,
    FAIL-FAST on a dimension mismatch (mirrors V1's qdrant_bootstrap guard — a silent re-embed at a
    wrong dim is a data-corruption trap)."""
    from qdrant_client.models import Distance, VectorParams  # lazy

    if client.collection_exists(collection):
        existing = client.get_collection(collection).config.params.vectors[_DENSE].size
        if existing != dim:
            raise RuntimeError(
                f"Qdrant collection {collection!r} has dim {existing}, embedder needs {dim} — refuse"
            )
        return
    client.create_collection(
        collection,
        vectors_config={_DENSE: VectorParams(size=dim, distance=Distance.COSINE)},
    )


def ingest_fachkarten(settings, *, client=None, embedder=None, catalog=None) -> int:
    """Embed every Fachkarten claim (``passage:``) + upsert into Qdrant. Idempotent (uuid5 point ids
    → re-seed overwrites; a claim flipping draft→reviewed updates in place). Returns #points upserted."""
    from qdrant_client.models import PointStruct  # lazy

    client = client or _make_client(settings)
    embedder = embedder or _make_embedder(settings)
    catalog = catalog or load_fachkarten()
    ensure_collection(client, settings.qdrant_collection, _embed_dim(embedder))
    items = list(claim_points(catalog))
    if not items:
        return 0
    pprefix = getattr(settings, "embed_passage_prefix", "passage: ")
    vectors = [
        v.tolist()
        for v in embedder.embed(
            [_passage_text(txt, pprefix) for _pid, txt, _p in items]
        )
    ]
    points = [
        PointStruct(id=pid, vector={_DENSE: vec}, payload=payload)
        for (pid, _txt, payload), vec in zip(items, vectors)
    ]
    client.upsert(settings.qdrant_collection, points=points)
    return len(points)


class QdrantFachkartenRetriever:
    """``Retriever`` Protocol impl — semantic Fachkarten recall over Qdrant. Drop-in for
    ``InProcessRetriever``: same async signature, same mandatory tenant, same RetrievalResult shape."""

    def __init__(self, settings, *, client=None, embedder=None) -> None:
        self._collection = settings.qdrant_collection
        self._client = client or _make_client(settings)
        self._embedder = embedder or _make_embedder(settings)
        self._qprefix = getattr(settings, "embed_query_prefix", "query: ")

    async def retrieve(
        self, query: str, *, tenant_id: str, k: int = 5
    ) -> RetrievalResult:
        if not (tenant_id or "").strip():
            raise ValueError("tenant_id is mandatory (P0 repository-layer scope)")
        import asyncio

        # FastEmbed (local ONNX) + the qdrant call are sync/CPU+IO → off the event loop in a thread.
        return await asyncio.to_thread(self._retrieve_sync, query, tenant_id, k)

    def _retrieve_sync(self, query: str, tenant_id: str, k: int) -> RetrievalResult:
        from qdrant_client.models import FieldCondition, Filter, MatchAny  # lazy

        qvec = next(
            iter(self._embedder.embed([_query_text(query, self._qprefix)]))
        ).tolist()
        tenant_filter = Filter(
            must=[
                FieldCondition(
                    key="tenant_id", match=MatchAny(any=[tenant_id, GLOBAL_TENANT])
                )
            ]
        )
        res = self._client.query_points(
            self._collection,
            query=qvec,
            using=_DENSE,
            limit=max(0, k),
            query_filter=tenant_filter,
            with_payload=True,
        )
        return _hits_to_result(res.points)
