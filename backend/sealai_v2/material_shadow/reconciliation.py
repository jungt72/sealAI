"""Bounded process-local reconciliation lease; Postgres remains authoritative."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from typing import Callable

from sealai_v2.core.material_shadow import ShadowReadinessState
from sealai_v2.material_shadow.resolver import (
    MaterialShadowResolver,
    ResolvedShadowSelection,
    ShadowRuntimeCompatibility,
)
from sealai_v2.core.contracts import VerifiedIdentity


@dataclass(frozen=True, slots=True)
class ShadowReconciliationLease:
    selection: ResolvedShadowSelection
    generation: int
    validated_monotonic: float
    expires_monotonic: float
    next_poll_monotonic: float


class ShadowReconciler:
    def __init__(
        self,
        resolver: MaterialShadowResolver,
        *,
        poll_s: int = 15,
        lease_s: int = 60,
        process_ref: str,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if poll_s <= 0 or lease_s <= poll_s:
            raise ValueError("shadow reconciliation requires 0 < poll < lease")
        self._resolver = resolver
        self._poll_s = poll_s
        self._lease_s = lease_s
        self._monotonic = monotonic
        jitter_seed = hashlib.sha256(process_ref.encode("utf-8")).digest()
        self._jitter_factor = (
            0.9 + (int.from_bytes(jitter_seed[:2], "big") / 65535) * 0.2
        )
        self._lease: ShadowReconciliationLease | None = None
        self._generation = 0

    def reconcile(
        self,
        *,
        enabled: bool,
        identity: VerifiedIdentity,
        runtime: ShadowRuntimeCompatibility,
        now_utc: str,
    ) -> ResolvedShadowSelection:
        now = self._monotonic()
        lease = self._lease
        if lease is not None and now < lease.next_poll_monotonic:
            if now >= lease.expires_monotonic:
                return ResolvedShadowSelection(ShadowReadinessState.EXPIRED_LEASE)
            return lease.selection
        try:
            selection = self._resolver.resolve(
                enabled=enabled, identity=identity, runtime=runtime, now=now_utc
            )
        except Exception:  # noqa: BLE001 - never revive the expired prior lease
            state = (
                ShadowReadinessState.EXPIRED_LEASE
                if lease is not None and now >= lease.expires_monotonic
                else ShadowReadinessState.DB_UNAVAILABLE
            )
            selection = ResolvedShadowSelection(state)
        self._generation += 1
        self._lease = ShadowReconciliationLease(
            selection=selection,
            generation=self._generation,
            validated_monotonic=now,
            expires_monotonic=now + self._lease_s,
            next_poll_monotonic=now + self._poll_s * self._jitter_factor,
        )
        return selection

    def expire(self) -> None:
        self._lease = None
