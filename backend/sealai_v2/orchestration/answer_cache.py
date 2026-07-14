"""Bounded exact-answer cache with an explicit mutable-authority epoch.

The cache is deliberately process-local.  A future Redis adapter must preserve
this contract: finite TTL, versioned authority-bound namespaces, per-tenant and
global cardinality bounds, and aggregate-only metrics.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from sealai_v2.core.contracts import Answer


AUTHORITY_EPOCH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_CACHE_TTL_SECONDS = 24 * 60 * 60
NAMESPACE_VERSION = "exact-answer.v2"


def build_answer_cache_namespace(
    *,
    authority_epoch: str,
    knowledge_version: str,
    policy_version: str,
    answer_contract_version: str,
    model_identity: str,
    structured_answers: bool,
) -> str:
    """Return a versioned namespace bound to the active authority snapshot.

    ``authority_epoch`` is an opaque canonical digest, never a timestamp or a
    human/tenant identifier.  Quarantine, revocation, expiry, or approval of a
    claim must produce a new digest before the cache may be used again.
    """

    if not AUTHORITY_EPOCH_RE.fullmatch(authority_epoch):
        raise ValueError("authority_epoch must be a canonical sha256 digest")
    components = (
        knowledge_version,
        policy_version,
        answer_contract_version,
        model_identity,
    )
    if any(not value or "\x00" in value for value in components):
        raise ValueError("cache namespace components must be non-empty")
    material = "\x00".join(
        (
            NAMESPACE_VERSION,
            authority_epoch,
            *components,
            f"structured={str(structured_answers).lower()}",
        )
    )
    return f"{NAMESPACE_VERSION}:sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def exact_answer_key(*, tenant_id: str, question: str, namespace: str) -> str:
    if not tenant_id or not namespace:
        raise ValueError("tenant_id and namespace are required")
    # Preserve exact Unicode code points and case. Technical symbols and
    # abbreviations can change meaning by case (for example Si versus SI).
    normalized = " ".join(question.split())
    material = f"{tenant_id}\x00{namespace}\x00{normalized}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Entry:
    answer: Answer
    expires_at: float


@dataclass(frozen=True)
class CacheMetrics:
    entries: int
    hits: int
    misses: int
    expirations: int
    capacity_evictions: int
    invalidated_entries: int

    @property
    def hit_rate(self) -> float:
        attempts = self.hits + self.misses
        return self.hits / attempts if attempts else 0.0


class InProcessExactAnswerCache:
    """TTL-bound LRU with both global and per-tenant cardinality ceilings."""

    def __init__(
        self,
        *,
        max_entries: int = 512,
        max_entries_per_tenant: int = 64,
        ttl_s: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or max_entries <= 0
        ):
            raise ValueError("max_entries must be a positive integer")
        if (
            isinstance(max_entries_per_tenant, bool)
            or not isinstance(max_entries_per_tenant, int)
            or max_entries_per_tenant <= 0
            or max_entries_per_tenant > max_entries
        ):
            raise ValueError("per-tenant cache bound must be within the global bound")
        if (
            isinstance(ttl_s, bool)
            or not isinstance(ttl_s, (int, float))
            or not math.isfinite(float(ttl_s))
            or ttl_s <= 0
            or ttl_s > MAX_CACHE_TTL_SECONDS
        ):
            raise ValueError("cache TTL must be finite and at most 24 hours")
        self._max_entries = max_entries
        self._max_entries_per_tenant = max_entries_per_tenant
        self._ttl_s = float(ttl_s)
        self._clock = clock
        self._entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._expirations = 0
        self._capacity_evictions = 0
        self._invalidated_entries = 0

    def get(self, *, tenant_id: str, key: str) -> Answer | None:
        cache_key = self._validated_key(tenant_id, key)
        entry = self._entries.get(cache_key)
        if entry is None:
            self._misses += 1
            return None
        if entry.expires_at <= self._clock():
            del self._entries[cache_key]
            self._expirations += 1
            self._misses += 1
            return None
        self._entries.move_to_end(cache_key)
        self._hits += 1
        return entry.answer

    def put(self, *, tenant_id: str, key: str, answer: Answer) -> None:
        cache_key = self._validated_key(tenant_id, key)
        self._entries[cache_key] = _Entry(
            answer=answer, expires_at=self._clock() + self._ttl_s
        )
        self._entries.move_to_end(cache_key)
        self._enforce_tenant_bound(tenant_id)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
            self._capacity_evictions += 1

    def invalidate_tenant(self, tenant_id: str) -> int:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        selected = [key for key in self._entries if key[0] == tenant_id]
        for key in selected:
            del self._entries[key]
        self._invalidated_entries += len(selected)
        return len(selected)

    def invalidate_all(self) -> int:
        removed = len(self._entries)
        self._entries.clear()
        self._invalidated_entries += removed
        return removed

    def metrics(self) -> CacheMetrics:
        return CacheMetrics(
            entries=len(self._entries),
            hits=self._hits,
            misses=self._misses,
            expirations=self._expirations,
            capacity_evictions=self._capacity_evictions,
            invalidated_entries=self._invalidated_entries,
        )

    @staticmethod
    def _validated_key(tenant_id: str, key: str) -> tuple[str, str]:
        if not tenant_id or not key:
            raise ValueError("tenant_id and key are required")
        return tenant_id, key

    def _enforce_tenant_bound(self, tenant_id: str) -> None:
        while (
            sum(1 for entry_key in self._entries if entry_key[0] == tenant_id)
            > self._max_entries_per_tenant
        ):
            oldest = next(
                entry_key for entry_key in self._entries if entry_key[0] == tenant_id
            )
            del self._entries[oldest]
            self._capacity_evictions += 1
