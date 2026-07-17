"""Redis-only cache for non-authoritative MAT-GOV-03B results."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from sealai_v2.core.material_shadow import ShadowMaterialRulesetPin


SHADOW_CACHE_NAMESPACE = "sealai:material-shadow:v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_CACHE_FIELDS = frozenset(
    {
        "evaluation_state",
        "verdict",
        "decisive_ref",
        "matches",
        "result_sha256",
        "stable_error_code",
    }
)


class ShadowCacheUnavailable(RuntimeError):
    pass


class ShadowCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, value: dict[str, Any], *, ttl_s: int) -> None: ...


def cache_key(
    *,
    pin: ShadowMaterialRulesetPin,
    input_fingerprint: str,
) -> str:
    components = (
        SHADOW_CACHE_NAMESPACE,
        pin.hmac_key_id,
        pin.tenant_ref_hmac,
        pin.snapshot_id,
        pin.content_sha256,
        pin.evaluator_version,
        pin.kernel_version,
        pin.domain_pack_id,
        pin.domain_pack_version,
        input_fingerprint,
        pin.sampling_policy_version,
    )
    if not _HEX64.fullmatch(input_fingerprint):
        raise ValueError("shadow input fingerprint must be lowercase SHA-256")
    if any(
        not component or any(ch.isspace() for ch in component)
        for component in components
    ):
        raise ValueError(
            "shadow cache key components must be stable non-whitespace IDs"
        )
    return ":".join(components)


def validate_cache_value(value: dict[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != _CACHE_FIELDS:
        raise ShadowCacheUnavailable("invalid material shadow cache schema")
    if type(value["matches"]) is not list or any(
        type(match) is not dict
        or frozenset(match) != {"rule_ref", "verdict", "source_ref"}
        or any(type(item) is not str for item in match.values())
        for match in value["matches"]
    ):
        raise ShadowCacheUnavailable("invalid material shadow cache matches")
    for field in (
        "evaluation_state",
        "stable_error_code",
    ):
        if type(value[field]) is not str or not value[field]:
            raise ShadowCacheUnavailable("invalid material shadow cache value")
    for field in ("verdict", "decisive_ref"):
        if value[field] is not None and type(value[field]) is not str:
            raise ShadowCacheUnavailable("invalid material shadow cache value")
    if not _HEX64.fullmatch(value["result_sha256"]):
        raise ShadowCacheUnavailable("invalid material shadow result hash")
    if value["stable_error_code"] != "none":
        raise ShadowCacheUnavailable("cache accepts only completed shadow results")
    if value["evaluation_state"] == "evaluated":
        if value["verdict"] not in {
            "vertraeglich",
            "unvertraeglich",
            "bedingt",
        }:
            raise ShadowCacheUnavailable("invalid material shadow verdict")
        if not value["matches"] or value["decisive_ref"] not in {
            match["rule_ref"] for match in value["matches"]
        }:
            raise ShadowCacheUnavailable("invalid material shadow decisive reference")
    elif value["evaluation_state"] in {"blocked", "no_rule_data"}:
        if value["verdict"] is not None or value["decisive_ref"] is not None:
            raise ShadowCacheUnavailable("non-evaluated cache result carries a verdict")
        if value["matches"]:
            raise ShadowCacheUnavailable("non-evaluated cache result carries matches")
    else:
        raise ShadowCacheUnavailable("invalid material shadow evaluation state")
    for match in value["matches"]:
        if (
            match["verdict"]
            not in {
                "vertraeglich",
                "unvertraeglich",
                "bedingt",
            }
            or match["source_ref"] != f"matrix-cell:{match['rule_ref']}"
        ):
            raise ShadowCacheUnavailable("invalid material shadow match reference")
    if len({match["rule_ref"] for match in value["matches"]}) != len(value["matches"]):
        raise ShadowCacheUnavailable("duplicate material shadow match reference")
    precedence = {"unvertraeglich": 0, "bedingt": 1, "vertraeglich": 2}
    canonical_matches = sorted(
        value["matches"],
        key=lambda match: (precedence[match["verdict"]], match["rule_ref"]),
    )
    if value["matches"] != canonical_matches:
        raise ShadowCacheUnavailable("material shadow matches are not canonical")
    if value["evaluation_state"] == "evaluated" and (
        value["verdict"] != value["matches"][0]["verdict"]
        or value["decisive_ref"] != value["matches"][0]["rule_ref"]
    ):
        raise ShadowCacheUnavailable("material shadow result precedence drift")
    # Defense in depth against future accidental content expansion.
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    forbidden = ("prompt", "question", "answer", "statement", "document", "email")
    if any(token in encoded.lower() for token in forbidden):
        raise ShadowCacheUnavailable("forbidden content in material shadow cache")
    return value


class RedisShadowCache:
    def __init__(self, client) -> None:
        self._client = client

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(key)
        except Exception as exc:  # noqa: BLE001 - converted to a stable shadow-only state
            raise ShadowCacheUnavailable("material shadow cache unavailable") from exc
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ShadowCacheUnavailable(
                "invalid material shadow cache encoding"
            ) from exc
        return validate_cache_value(value)

    def put(self, key: str, value: dict[str, Any], *, ttl_s: int) -> None:
        clean = validate_cache_value(value)
        if type(ttl_s) is not int or ttl_s <= 0:
            raise ValueError("shadow cache TTL must be positive")
        raw = json.dumps(clean, separators=(",", ":"), sort_keys=True)
        try:
            self._client.setex(key, ttl_s, raw)
        except Exception as exc:  # noqa: BLE001 - converted to a stable shadow-only state
            raise ShadowCacheUnavailable("material shadow cache unavailable") from exc
