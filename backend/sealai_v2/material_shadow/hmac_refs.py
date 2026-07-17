"""Versioned tenant-bound HMAC references for MAT-GOV-03B."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import struct

from sealai_v2.core.material_shadow import ShadowErrorCode, ShadowContractError


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$", re.ASCII)
_UINT32_MAX = (1 << 32) - 1

TENANT_REF_DOMAIN = b"sealai.material-shadow.tenant-ref.v1"
SESSION_REF_DOMAIN = b"sealai.material-shadow.session-ref.v1"
REQUEST_REF_DOMAIN = b"sealai.material-shadow.request-ref.v1"
CASE_REF_DOMAIN = b"sealai.material-shadow.case-ref.v1"
DECISION_REF_DOMAIN = b"sealai.material-shadow.decision-ref.v1"
SAMPLING_REF_DOMAIN = b"sealai.material-shadow.sampling-ref.v1"
BINDING_LOCK_DOMAIN = b"sealai.material-shadow.binding-lock.v1"
_ALLOWED_DOMAINS = frozenset(
    {
        BINDING_LOCK_DOMAIN,
        TENANT_REF_DOMAIN,
        SESSION_REF_DOMAIN,
        REQUEST_REF_DOMAIN,
        CASE_REF_DOMAIN,
        DECISION_REF_DOMAIN,
        SAMPLING_REF_DOMAIN,
    }
)


def encode_hmac_fields(domain: bytes, fields: tuple[str, ...]) -> bytes:
    """Encode one typed HMAC tuple without delimiter or normalization ambiguity."""

    if type(domain) is not bytes or domain not in _ALLOWED_DOMAINS:
        raise ValueError("unknown material shadow HMAC domain")
    if type(fields) is not tuple or any(type(field) is not str for field in fields):
        raise TypeError("material shadow HMAC fields must be a tuple of strings")
    encoded_fields = tuple(field.encode("utf-8", errors="strict") for field in fields)
    if any(len(field) > _UINT32_MAX for field in encoded_fields):
        raise ValueError("material shadow HMAC field exceeds uint32 length")
    payload = bytearray(domain)
    payload.append(0)
    for field in encoded_fields:
        payload.extend(struct.pack(">I", len(field)))
        payload.extend(field)
    return bytes(payload)


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate HMAC keyring key")
        value[key] = item
    return value


class ShadowHmacKeyring:
    def __init__(self, keys: dict[str, str], *, active_key_id: str) -> None:
        if not _KEY_ID.fullmatch(active_key_id):
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "invalid active hmac_key_id"
            )
        clean: dict[str, bytes] = {}
        for key_id, secret in keys.items():
            if not _KEY_ID.fullmatch(key_id) or type(secret) is not str:
                raise ShadowContractError(
                    ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "invalid HMAC keyring"
                )
            encoded = secret.encode("utf-8")
            if len(encoded) < 32:
                raise ShadowContractError(
                    ShadowErrorCode.HMAC_KEY_UNAVAILABLE,
                    "HMAC secrets must contain at least 32 UTF-8 bytes",
                )
            clean[key_id] = encoded
        if active_key_id not in clean:
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE,
                "active hmac_key_id is absent from the keyring",
            )
        self._keys = clean
        self.active_key_id = active_key_id

    @classmethod
    def from_json(cls, raw: str, *, active_key_id: str) -> "ShadowHmacKeyring":
        try:
            parsed = json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
        except (TypeError, ValueError) as exc:
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "malformed HMAC keyring"
            ) from exc
        if type(parsed) is not dict or any(
            type(key) is not str or type(value) is not str
            for key, value in parsed.items()
        ):
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "malformed HMAC keyring"
            )
        return cls(parsed, active_key_id=active_key_id)

    def digest_fields(
        self,
        domain: bytes,
        fields: tuple[str, ...],
        *,
        key_id: str | None = None,
    ) -> str:
        selected = self.active_key_id if key_id is None else key_id
        key = self._keys.get(selected)
        if key is None:
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "unknown hmac_key_id"
            )
        payload = encode_hmac_fields(domain, fields)
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    def contains(self, key_id: str) -> bool:
        return key_id in self._keys

    def references_fields(
        self, domain: bytes, fields: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]:
        """Return deterministic key-versioned references without exposing keys."""

        return tuple(
            (key_id, self.digest_fields(domain, fields, key_id=key_id))
            for key_id in sorted(self._keys)
        )
