"""Bounded process-local reconciliation lease; Postgres remains authoritative."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from threading import RLock
import time
from typing import Callable

from sealai_v2.core.material_rulesets import validate_domain_pack_id
from sealai_v2.core.material_shadow import (
    ShadowEnvironment,
    ShadowPurpose,
    ShadowReadinessState,
    ShadowScopeKind,
)
from sealai_v2.material_shadow.hmac_refs import TENANT_REF_DOMAIN, ShadowHmacKeyring
from sealai_v2.material_shadow.resolver import (
    MaterialShadowResolver,
    ResolvedShadowSelection,
    ShadowRuntimeCompatibility,
)
from sealai_v2.core.contracts import VerifiedIdentity


_HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_BINDING_ID = re.compile(r"^mshb_[0-9a-f]{32}$", re.ASCII)
_STABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)


@dataclass(frozen=True, slots=True)
class ShadowReconciliationRequestKey:
    tenant_ref_hmac: str
    hmac_key_id: str
    environment: ShadowEnvironment
    purpose: ShadowPurpose
    domain_pack_id: str
    domain_pack_version: str
    runtime_profile_sha256: str
    build_git_sha: str
    build_tree_hash: str
    evaluator_version: str
    kernel_version: str

    def __post_init__(self) -> None:
        if not _HEX64.fullmatch(self.tenant_ref_hmac):
            raise ValueError("reconciliation tenant reference must be SHA-256")
        if not _STABLE.fullmatch(self.hmac_key_id):
            raise ValueError("reconciliation hmac_key_id is required")
        if type(self.environment) is not ShadowEnvironment:
            raise TypeError("reconciliation environment must be typed")
        if self.purpose is not ShadowPurpose.MATERIAL_RULESET_SHADOW:
            raise ValueError("reconciliation purpose is fixed")
        validate_domain_pack_id(self.domain_pack_id)
        if not _HEX64.fullmatch(self.runtime_profile_sha256):
            raise ValueError("invalid reconciliation runtime profile hash")
        if not _HEX40.fullmatch(self.build_git_sha) or not _HEX40.fullmatch(
            self.build_tree_hash
        ):
            raise ValueError("invalid reconciliation build identity")
        for value in (
            self.domain_pack_version,
            self.evaluator_version,
            self.kernel_version,
        ):
            if type(value) is not str or not _STABLE.fullmatch(value):
                raise ValueError("reconciliation partition fields must be non-empty")


@dataclass(frozen=True, slots=True)
class ShadowReconciliationPartitionKey:
    request: ShadowReconciliationRequestKey
    scope_kind: ShadowScopeKind | None
    binding_id: str | None

    def __post_init__(self) -> None:
        if type(self.request) is not ShadowReconciliationRequestKey:
            raise TypeError("reconciliation request key is required")
        if self.binding_id is None:
            if self.scope_kind is not None:
                raise ValueError("unbound reconciliation partition has a scope")
            return
        if type(self.scope_kind) is not ShadowScopeKind:
            raise TypeError("bound reconciliation partition requires scope_kind")
        if not _BINDING_ID.fullmatch(self.binding_id):
            raise ValueError("invalid reconciliation binding_id")


@dataclass(frozen=True, slots=True)
class ShadowReconciliationLease:
    partition: ShadowReconciliationPartitionKey
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
        keyring: ShadowHmacKeyring,
        poll_s: int = 15,
        lease_s: int = 60,
        process_ref: str,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if poll_s <= 0 or lease_s <= poll_s:
            raise ValueError("shadow reconciliation requires 0 < poll < lease")
        self._resolver = resolver
        if not isinstance(keyring, ShadowHmacKeyring):
            raise TypeError("shadow reconciliation requires a HMAC keyring")
        self._keyring = keyring
        self._poll_s = poll_s
        self._lease_s = lease_s
        self._monotonic = monotonic
        jitter_seed = hashlib.sha256(process_ref.encode("utf-8")).digest()
        self._jitter_factor = (
            0.9 + (int.from_bytes(jitter_seed[:2], "big") / 65535) * 0.2
        )
        self._leases: dict[
            ShadowReconciliationPartitionKey, ShadowReconciliationLease
        ] = {}
        self._partitions: dict[
            ShadowReconciliationRequestKey, ShadowReconciliationPartitionKey
        ] = {}
        self._lock = RLock()
        self._generation = 0

    def _request_key(
        self, identity: VerifiedIdentity, runtime: ShadowRuntimeCompatibility
    ) -> ShadowReconciliationRequestKey:
        tenant_ref = self._keyring.digest_fields(
            TENANT_REF_DOMAIN,
            (identity.tenant_id,),
        )
        return ShadowReconciliationRequestKey(
            tenant_ref_hmac=tenant_ref,
            hmac_key_id=self._keyring.active_key_id,
            environment=runtime.environment,
            purpose=ShadowPurpose.MATERIAL_RULESET_SHADOW,
            domain_pack_id=runtime.domain_pack_id,
            domain_pack_version=runtime.domain_pack_version,
            runtime_profile_sha256=runtime.runtime_profile_sha256,
            build_git_sha=runtime.build_git_sha,
            build_tree_hash=runtime.build_tree_hash,
            evaluator_version=runtime.evaluator_version,
            kernel_version=runtime.kernel_version,
        )

    @staticmethod
    def _partition_key(
        request: ShadowReconciliationRequestKey,
        selection: ResolvedShadowSelection,
    ) -> ShadowReconciliationPartitionKey:
        binding = selection.binding
        if binding is None:
            return ShadowReconciliationPartitionKey(request, None, None)
        return ShadowReconciliationPartitionKey(
            request,
            binding.scope_kind,
            binding.binding_id,
        )

    def _remove_partition(self, request: ShadowReconciliationRequestKey) -> None:
        partition = self._partitions.pop(request, None)
        if partition is not None:
            self._leases.pop(partition, None)

    def _purge_expired(
        self,
        now: float,
        *,
        keep: ShadowReconciliationPartitionKey | None = None,
    ) -> None:
        expired = {
            partition
            for partition, lease in self._leases.items()
            if partition != keep and now >= lease.expires_monotonic
        }
        if not expired:
            return
        for partition in expired:
            self._leases.pop(partition, None)
        for request, partition in tuple(self._partitions.items()):
            if partition in expired:
                self._partitions.pop(request, None)

    def reconcile(
        self,
        *,
        enabled: bool,
        identity: VerifiedIdentity,
        runtime: ShadowRuntimeCompatibility,
        now_utc: str,
    ) -> ResolvedShadowSelection:
        if not enabled:
            return ResolvedShadowSelection(ShadowReadinessState.DISABLED)
        if not isinstance(identity, VerifiedIdentity):
            raise TypeError("reconciliation identity must be verified")
        if not isinstance(runtime, ShadowRuntimeCompatibility):
            raise TypeError("reconciliation runtime must be typed")
        request = self._request_key(identity, runtime)
        now = self._monotonic()
        with self._lock:
            partition = self._partitions.get(request)
            self._purge_expired(now, keep=partition)
            lease = self._leases.get(partition) if partition is not None else None
            if lease is not None and now < lease.next_poll_monotonic:
                if now >= lease.expires_monotonic:
                    return ResolvedShadowSelection(ShadowReadinessState.EXPIRED_LEASE)
                return lease.selection
            try:
                selection = self._resolver.resolve(
                    enabled=True, identity=identity, runtime=runtime, now=now_utc
                )
            except Exception:  # noqa: BLE001 - never revive the expired prior lease
                state = (
                    ShadowReadinessState.EXPIRED_LEASE
                    if lease is not None and now >= lease.expires_monotonic
                    else ShadowReadinessState.DB_UNAVAILABLE
                )
                selection = ResolvedShadowSelection(state)
            self._remove_partition(request)
            partition = self._partition_key(request, selection)
            self._generation += 1
            self._partitions[request] = partition
            self._leases[partition] = ShadowReconciliationLease(
                partition=partition,
                selection=selection,
                generation=self._generation,
                validated_monotonic=now,
                expires_monotonic=now + self._lease_s,
                next_poll_monotonic=now + self._poll_s * self._jitter_factor,
            )
            return selection

    def expire(self) -> None:
        with self._lock:
            self._leases.clear()
            self._partitions.clear()
