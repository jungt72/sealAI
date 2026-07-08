"""Legal-by-Design Phase C (Goal 5): tenant-isolation guardrails for the RAG/Qdrant layer, using
the shared ``assert_tenant_scoped_query`` helper (``tests/_tenant_assertions.py``).

Context (from the Legal-by-Design audit): there is currently NO customer-upload ingestion endpoint
anywhere in the codebase — the only Qdrant WRITE path is ``ingest_fachkarten`` (owner-curated
Fachkarten knowledge, hardcoded ``tenant_id=GLOBAL_TENANT``, see ``knowledge/qdrant_retrieval.py``).
These tests are therefore deliberately PREVENTIVE: they lock in the tenant-scoping contract NOW, so
that if/when a customer-upload feature is ever built, a regression in this contract is caught
immediately rather than discovered after real customer data has already crossed a tenant boundary.
"""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.qdrant_retrieval import (
    GLOBAL_TENANT,
    QdrantFachkartenRetriever,
    claim_points,
    delete_card_points,
    ingest_fachkarten,
)
from sealai_v2.tests._tenant_assertions import assert_tenant_scoped_query


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


class _ListLike(list):
    def tolist(self):
        return list(self)


class _FakeDenseEmbedder:
    def embed(self, texts):
        return [_ListLike([0.1, 0.2, 0.3]) for _ in texts]


def _retriever(**settings_kwargs) -> tuple[QdrantFachkartenRetriever, _FakeClient]:
    client = _FakeClient(points=[])
    r = QdrantFachkartenRetriever(
        Settings(**settings_kwargs),
        client=client,
        embedder=_FakeDenseEmbedder(),
    )
    return r, client


def test_retrieve_query_is_scoped_to_the_calling_tenant_and_global():
    r, client = _retriever()
    asyncio.run(r.retrieve("PTFE Dichtung", tenant_id="tenant-A", k=5))
    assert_tenant_scoped_query(
        client.last_query_points_kwargs["query_filter"],
        "tenant-A",
        global_tenant=GLOBAL_TENANT,
    )


def test_retrieve_scope_changes_with_the_calling_tenant_not_a_fixed_value():
    # The filter must reflect THIS call's tenant, not some baked-in default — proves the scope is
    # actually derived from the argument, not accidentally hardcoded to one tenant.
    r, client = _retriever()
    asyncio.run(r.retrieve("PTFE Dichtung", tenant_id="tenant-B", k=5))
    assert_tenant_scoped_query(
        client.last_query_points_kwargs["query_filter"],
        "tenant-B",
        global_tenant=GLOBAL_TENANT,
    )
    with pytest.raises(AssertionError):
        assert_tenant_scoped_query(
            client.last_query_points_kwargs["query_filter"],
            "tenant-A",  # wrong tenant — must NOT match tenant-B's actual filter
            global_tenant=GLOBAL_TENANT,
        )


def test_retrieve_missing_tenant_id_is_a_hard_error_not_a_silent_wildcard():
    r, _client = _retriever()
    with pytest.raises(ValueError, match="tenant_id is mandatory"):
        asyncio.run(r.retrieve("x", tenant_id="", k=5))


def test_hybrid_retrieve_is_also_tenant_scoped():
    # The hybrid (dense+sparse RRF) path builds its query differently (FusionQuery/prefetch) —
    # confirm the SAME tenant_id filter still applies to the outer query_points call.
    from sealai_v2.knowledge.qdrant_retrieval import GLOBAL_TENANT as _GT

    class _FakeSparseEmbedding:
        def __init__(self, indices, values):
            self.indices = _ListLike(indices)
            self.values = _ListLike(values)

    class _FakeSparseEmbedder:
        def embed(self, texts):
            return [_FakeSparseEmbedding([1, 2], [0.5, 0.5]) for _ in texts]

    client = _FakeClient(points=[])
    r = QdrantFachkartenRetriever(
        Settings(qdrant_hybrid_enabled=True),
        client=client,
        embedder=_FakeDenseEmbedder(),
        sparse_embedder=_FakeSparseEmbedder(),
    )
    asyncio.run(r.retrieve("PTFE Dichtung", tenant_id="tenant-A", k=5))
    assert_tenant_scoped_query(
        client.last_query_points_kwargs["query_filter"], "tenant-A", global_tenant=_GT
    )


def test_ingest_fachkarten_only_writes_to_the_global_tenant_scope():
    # The only current Qdrant WRITE path — proves it can NEVER write a customer/tenant-specific
    # point today (no tenant_id parameter exists on claim_points/ingest_fachkarten at all).
    import inspect

    sig = inspect.signature(claim_points)
    assert "tenant_id" not in sig.parameters, (
        "claim_points gained a tenant_id parameter — re-verify it cannot be used to write "
        "customer data into the GLOBAL_TENANT scope without an explicit, documented promotion step"
    )
    ingest_sig = inspect.signature(ingest_fachkarten)
    assert "tenant_id" not in ingest_sig.parameters


def test_delete_card_points_has_no_tenant_parameter_either():
    # Same structural guardrail for the delete path — a future cross-tenant delete bug would need
    # to ADD a tenant_id param first, which this test would then force a deliberate review of.
    import inspect

    assert "tenant_id" not in inspect.signature(delete_card_points).parameters
