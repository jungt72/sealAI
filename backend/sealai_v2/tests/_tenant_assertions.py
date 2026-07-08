"""Legal-by-Design Phase C (Goal 5): a reusable assertion helper proving a Qdrant query is
tenant-scoped — used by tests across this suite so "is this retrieval call tenant-scoped?" is
answered the SAME way everywhere, instead of each test hand-rolling its own Filter introspection.

NOT a test module itself (no ``test_`` prefix — mirrors ``tests/_apiutil.py`` / ``tests/_fakes.py``'s
existing underscore-prefixed non-test-module convention).

Scope note: this asserts the CONTRACT sealingAI's own code builds (the ``Filter``/``MatchAny``
object handed to ``qdrant_client``) — it does not re-test Qdrant's own filter engine (a real,
independently-tested vector DB), which is out of scope for a unit test here.
"""

from __future__ import annotations


def assert_tenant_scoped_query(
    query_filter, tenant_id: str, *, global_tenant: str
) -> None:
    """Asserts ``query_filter`` (a ``qdrant_client.models.Filter``) restricts the query to exactly
    ``{tenant_id, global_tenant}`` on the ``tenant_id`` field — no other tenant, no wildcard/absent
    filter. Raises ``AssertionError`` with a precise message on any deviation."""
    from qdrant_client.models import FieldCondition, MatchAny

    assert (
        query_filter is not None
    ), "query has NO filter at all — would match every tenant"
    conditions = list(query_filter.must or ())
    tenant_conditions = [
        c for c in conditions if isinstance(c, FieldCondition) and c.key == "tenant_id"
    ]
    assert tenant_conditions, "query filter has no tenant_id FieldCondition at all"
    assert (
        len(tenant_conditions) == 1
    ), "multiple tenant_id conditions — ambiguous scoping"
    match = tenant_conditions[0].match
    assert isinstance(
        match, MatchAny
    ), f"tenant_id condition is not a MatchAny: {match!r}"
    allowed = set(match.any)
    expected = {tenant_id, global_tenant}
    assert allowed == expected, (
        f"tenant_id MatchAny scope {allowed!r} != expected {expected!r} "
        f"(either a missing tenant/global entry, or an EXTRA/leaked tenant id)"
    )
