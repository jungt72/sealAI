"""Domain-separated Redis cache for MAT-EVID-01B shadow evaluations."""

from __future__ import annotations

import base64
import binascii
import json
import re
import struct
from typing import Protocol

from sealai_v2.core.material_evidence_binding import EvidenceRuntimePinV1
from sealai_v2.core.material_shadow import ShadowMaterialRulesetPin
from sealai_v2.material_evidence_binding.evaluator import EvidenceRuntimeEvaluationV1


EVIDENCE_CACHE_NAMESPACE = "mat-evid-bind:v1:"
_CACHE_DOMAIN = b"sealai.material-evidence.runtime-cache-key.v1"
_SEGMENT_COUNT = 19
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class EvidenceRuntimeCacheUnavailable(RuntimeError):
    pass


class EvidenceRuntimeCache(Protocol):
    def get(self, key: str) -> EvidenceRuntimeEvaluationV1 | None: ...

    def put(
        self, key: str, value: EvidenceRuntimeEvaluationV1, *, ttl_s: int
    ) -> None: ...


def _encode(segments: tuple[str, ...]) -> str:
    if len(segments) != _SEGMENT_COUNT:
        raise ValueError("runtime evidence cache segment count is fixed")
    values = (_CACHE_DOMAIN, *(item.encode("utf-8") for item in segments))
    payload = bytearray(struct.pack(">I", len(values)))
    for value in values:
        payload.extend(struct.pack(">I", len(value)))
        payload.extend(value)
    token = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return f"{EVIDENCE_CACHE_NAMESPACE}{token}"


def _is_current(key: object) -> bool:
    if type(key) is not str or not key.startswith(EVIDENCE_CACHE_NAMESPACE):
        return False
    token = key.removeprefix(EVIDENCE_CACHE_NAMESPACE)
    try:
        raw = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error):
        return False
    if len(raw) < 4 or struct.unpack_from(">I", raw)[0] != _SEGMENT_COUNT + 1:
        return False
    offset = 4
    segments: list[bytes] = []
    for _index in range(_SEGMENT_COUNT + 1):
        if offset + 4 > len(raw):
            return False
        length = struct.unpack_from(">I", raw, offset)[0]
        offset += 4
        if offset + length > len(raw):
            return False
        segments.append(raw[offset : offset + length])
        offset += length
    return offset == len(raw) and segments[0] == _CACHE_DOMAIN


def evidence_cache_key(
    *,
    shadow_pin: ShadowMaterialRulesetPin,
    evidence_pin: EvidenceRuntimePinV1,
    input_fingerprint: str,
) -> str:
    binding = evidence_pin.binding
    if evidence_pin.pin_id != shadow_pin.pin_id:
        raise ValueError("shadow and evidence pins differ")
    if (
        binding.binding_id != shadow_pin.binding_id
        or binding.ruleset_snapshot_id != shadow_pin.snapshot_id
        or binding.ruleset_content_sha256 != shadow_pin.content_sha256
        or binding.domain_pack_id != shadow_pin.domain_pack_id
        or binding.domain_pack_version != shadow_pin.domain_pack_version
        or binding.evaluator_version != shadow_pin.evaluator_version
        or binding.kernel_version != shadow_pin.kernel_version
    ):
        raise ValueError("shadow and evidence pin identities drift")
    if not _HEX64.fullmatch(input_fingerprint):
        raise ValueError("input_fingerprint must be lowercase SHA-256")
    unbound = "<UNBOUND>"
    segments = (
        shadow_pin.hmac_key_id,
        shadow_pin.tenant_ref_hmac,
        shadow_pin.snapshot_id,
        shadow_pin.content_sha256,
        binding.evidence_snapshot_id or unbound,
        binding.evidence_content_sha256 or unbound,
        binding.state.value,
        binding.binding_contract_version,
        binding.evidence_contract_version or unbound,
        str(binding.evidence_manifest_schema_version or unbound),
        str(binding.evidence_canonicalization_version or unbound),
        shadow_pin.evaluator_version,
        shadow_pin.kernel_version,
        shadow_pin.domain_pack_id,
        shadow_pin.domain_pack_version,
        shadow_pin.runtime_profile_sha256,
        shadow_pin.build_git_sha,
        shadow_pin.build_tree_hash,
        input_fingerprint,
    )
    if any(
        not item or any(character.isspace() for character in item) for item in segments
    ):
        raise ValueError("runtime evidence cache segments must be stable")
    return _encode(segments)


class RedisEvidenceRuntimeCache:
    def __init__(self, client) -> None:
        self._client = client

    def get(self, key: str) -> EvidenceRuntimeEvaluationV1 | None:
        if not _is_current(key):
            return None
        try:
            raw = self._client.get(key)
        except Exception as exc:  # noqa: BLE001 - stable isolated cache failure
            raise EvidenceRuntimeCacheUnavailable(
                "runtime evidence cache unavailable"
            ) from exc
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            return EvidenceRuntimeEvaluationV1.from_dict(value)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise EvidenceRuntimeCacheUnavailable(
                "invalid runtime evidence cache value"
            ) from exc

    def put(self, key: str, value: EvidenceRuntimeEvaluationV1, *, ttl_s: int) -> None:
        if not _is_current(key):
            raise ValueError("runtime evidence cache key is outside the current domain")
        if type(value) is not EvidenceRuntimeEvaluationV1:
            raise TypeError("value must be EvidenceRuntimeEvaluationV1")
        if value.evaluation_state == "integrity_blocked":
            raise ValueError("integrity-blocked results are never cached")
        if type(ttl_s) is not int or ttl_s <= 0:
            raise ValueError("runtime evidence cache TTL must be positive")
        raw = json.dumps(value.to_dict(), separators=(",", ":"), sort_keys=True)
        try:
            self._client.setex(key, ttl_s, raw)
        except Exception as exc:  # noqa: BLE001 - stable isolated cache failure
            raise EvidenceRuntimeCacheUnavailable(
                "runtime evidence cache unavailable"
            ) from exc


__all__ = [
    "EVIDENCE_CACHE_NAMESPACE",
    "EvidenceRuntimeCache",
    "EvidenceRuntimeCacheUnavailable",
    "RedisEvidenceRuntimeCache",
    "evidence_cache_key",
]
