"""Memory retrieval — sealingAI Memory Architecture V1.0, Patch 6.

Answers the architecture question from the source prompt directly: "wie stellen wir sicher, dass
rejected oder deleted nicht weiter aus Qdrant kommen?" — NOT durch Vertrauen in Qdrant. Three
layers: (1) Qdrant payload mirrors status/scope/tenant/version (Patch 5); (2) the outbox pattern
guarantees every status change enqueues a sync (Patch 4/5); (3) THIS module — every Qdrant result
is re-checked against LIVE Postgres before it may ever reach a prompt. Layer 3 is the one that
actually matters: layers 1-2 keep Qdrant USUALLY fresh, but "usually" is not a safety guarantee — a
failed/delayed outbox sync (Patch 5's own retry-then-permanently-failed path) means Qdrant CAN be
stale, and this module is what makes that survivable rather than a leak.

Qdrant's payload is therefore NEVER READ here for the injectability decision (``with_payload=False``
on the query itself — not just "ignored", genuinely not fetched, so there is no code path that could
accidentally trust it). Only the point id is used, purely to look the SAME item up fresh in Postgres.
"""

from __future__ import annotations

from sealai_v2.db.memory_store import MemoryStore
from sealai_v2.memory.curated import MemoryItem
from sealai_v2.memory.outbox_worker import MEMORY_COLLECTION

_DENSE = "dense"
# Qdrant candidates are over-fetched relative to k because revalidation WILL discard some (stale
# rejected/deprecated/deleted items, or items purged since the point was indexed) — without this
# margin a query could return fewer than k results even though k valid items actually exist.
_CANDIDATE_OVERFETCH_FACTOR = 4


def revalidate(
    candidate_ids: list[str],
    *,
    tenant_id: str,
    store: MemoryStore,
    now: str,
) -> tuple[MemoryItem, ...]:
    """PURE aside from the injected ``store`` (a duck-typed read, no Qdrant/network here) — every
    candidate id is looked up fresh; anything missing (purged, or never existed), not injectable
    (rejected/deprecated/deleted_pending_purge/purged — ``MemoryItem.is_injectable``), or past its
    ``purge_after`` (an "expired" defense-in-depth check even though DELETED_PENDING_PURGE is
    already excluded by ``is_injectable`` — belt and suspenders per the source prompt's explicit
    "rejected/deprecated/deleted/expired" wording) is silently dropped, never surfaced as an error —
    a stale Qdrant hit disappearing is the CORRECT, honest outcome (Leitsatz L5: the system says
    what it doesn't know, it doesn't guess around a gap)."""
    valid: list[MemoryItem] = []
    for item_id in candidate_ids:
        item = store.get_item(tenant_id=tenant_id, item_id=item_id)
        if item is None:
            continue
        if not item.is_injectable:
            continue
        if item.purge_after is not None and item.purge_after <= now:
            continue
        valid.append(item)
    return tuple(valid)


def retrieve_memory(
    query: str,
    *,
    tenant_id: str,
    qdrant_client,
    embedder,
    store: MemoryStore,
    now: str,
    k: int = 5,
) -> tuple[MemoryItem, ...]:
    """Qdrant top-k with a HARD tenant filter (server-side, never client-supplied — same P0
    discipline as Fachkarten retrieval), then mandatory Postgres revalidation. Returns AUTHORITATIVE
    ``MemoryItem`` objects (freshly read from Postgres, not whatever Qdrant's payload said)."""
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    qvec = next(iter(embedder.embed([query]))).tolist()
    tenant_filter = Filter(
        must=[FieldCondition(key="tenant_id", match=MatchAny(any=[tenant_id]))]
    )
    res = qdrant_client.query_points(
        MEMORY_COLLECTION,
        query=qvec,
        using=_DENSE,
        limit=max(k, k * _CANDIDATE_OVERFETCH_FACTOR),
        query_filter=tenant_filter,
        with_payload=False,  # deliberately unread — see module docstring
    )
    candidate_ids = [str(p.id) for p in res.points]
    valid = revalidate(candidate_ids, tenant_id=tenant_id, store=store, now=now)
    return valid[:k]
