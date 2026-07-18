"""Deterministic, owner-frozen MAT-GOV-03B sampling."""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.material_shadow.hmac_refs import (
    SAMPLING_REF_DOMAIN,
    ShadowHmacKeyring,
)


@dataclass(frozen=True, slots=True)
class ShadowSamplingDecision:
    policy_version: str
    basis_points: int
    sampled: bool


def decide_sampling(
    *,
    tenant_id: str,
    session_ref: str,
    policy_version: str,
    basis_points: int,
    keyring: ShadowHmacKeyring,
) -> ShadowSamplingDecision:
    if basis_points != 0:
        raise ValueError("MAT-GOV-03B sampling is owner-frozen at zero percent")
    # Still derive the stable bucket to prove request/result independence and
    # keep the contract ready for a separately owner-authorized future policy.
    digest = keyring.digest_fields(
        SAMPLING_REF_DOMAIN,
        (tenant_id, session_ref, policy_version),
    )
    _bucket = int(digest[:8], 16) % 10_000
    return ShadowSamplingDecision(policy_version, basis_points, False)
