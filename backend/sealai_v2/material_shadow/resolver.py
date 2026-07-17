"""Deterministic pointerless resolver for one exact shadow binding."""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_rulesets import MaterialRulesetIntegrityError
from sealai_v2.core.material_shadow import (
    ShadowBinding,
    ShadowEnvironment,
    ShadowReadinessState,
)
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.material_shadow.hmac_refs import ShadowHmacKeyring


@dataclass(frozen=True, slots=True)
class ShadowRuntimeCompatibility:
    environment: ShadowEnvironment
    domain_pack_id: str
    domain_pack_version: str
    evaluator_version: str
    kernel_version: str
    runtime_profile_sha256: str
    build_git_sha: str
    build_tree_hash: str


@dataclass(frozen=True, slots=True)
class ResolvedShadowSelection:
    state: ShadowReadinessState
    binding: ShadowBinding | None = None

    def __post_init__(self) -> None:
        if self.state is ShadowReadinessState.READY and self.binding is None:
            raise ValueError("ready shadow selection requires a binding")
        if self.state is not ShadowReadinessState.READY and self.binding is not None:
            raise ValueError("non-ready selection cannot carry a binding")


class MaterialShadowResolver:
    def __init__(
        self,
        *,
        repository: MaterialShadowRepository,
        rulesets: MaterialRulesetRepository,
        keyring: ShadowHmacKeyring,
    ) -> None:
        self._repository = repository
        self._rulesets = rulesets
        self._keyring = keyring

    def resolve(
        self,
        *,
        enabled: bool,
        identity: VerifiedIdentity,
        runtime: ShadowRuntimeCompatibility,
        now: str,
    ) -> ResolvedShadowSelection:
        if not enabled:
            return ResolvedShadowSelection(ShadowReadinessState.DISABLED)
        try:
            tenant_references = self._keyring.references(
                f"tenant\x00{identity.tenant_id}"
            )
            canary = self._repository.current_candidates(
                environment=runtime.environment.value,
                tenant_references=tenant_references,
                domain_pack_id=runtime.domain_pack_id,
                now=now,
                tenant_tier=True,
            )
            if len(canary) > 1:
                return ResolvedShadowSelection(ShadowReadinessState.AMBIGUOUS_BINDING)
            if canary:
                row = canary[0]
                # A present but invalid canary never falls back to global.
                if self._repository.binding_is_terminal(row.binding_id, now=now):
                    return ResolvedShadowSelection(ShadowReadinessState.NO_BINDING)
            else:
                global_candidates = self._repository.current_candidates(
                    environment=runtime.environment.value,
                    tenant_references=tenant_references,
                    domain_pack_id=runtime.domain_pack_id,
                    now=now,
                    tenant_tier=False,
                )
                if len(global_candidates) > 1:
                    return ResolvedShadowSelection(
                        ShadowReadinessState.AMBIGUOUS_BINDING
                    )
                if not global_candidates:
                    return ResolvedShadowSelection(ShadowReadinessState.NO_BINDING)
                row = global_candidates[0]
                if self._repository.binding_is_terminal(row.binding_id, now=now):
                    return ResolvedShadowSelection(ShadowReadinessState.NO_BINDING)
            binding = self._repository.binding_from_row(row)
            snapshot = self._rulesets.load_snapshot(binding.snapshot_id)
            if (
                snapshot.content_sha256 != binding.content_sha256
                or snapshot.payload.domain_pack_id != binding.domain_pack_id
            ):
                return ResolvedShadowSelection(ShadowReadinessState.SNAPSHOT_DRIFT)
            compatible = (
                binding.environment is runtime.environment
                and binding.domain_pack_version == runtime.domain_pack_version
                and binding.evaluator_version == runtime.evaluator_version
                and binding.kernel_version == runtime.kernel_version
                and binding.runtime_profile_sha256 == runtime.runtime_profile_sha256
                and binding.build_git_sha == runtime.build_git_sha
                and binding.build_tree_hash == runtime.build_tree_hash
            )
            if not compatible:
                return ResolvedShadowSelection(
                    ShadowReadinessState.EVALUATOR_INCOMPATIBLE
                )
            return ResolvedShadowSelection(ShadowReadinessState.READY, binding)
        except MaterialRulesetIntegrityError:
            return ResolvedShadowSelection(ShadowReadinessState.SNAPSHOT_DRIFT)
        except Exception:  # noqa: BLE001 - never escapes into the primary path
            return ResolvedShadowSelection(ShadowReadinessState.DB_UNAVAILABLE)
