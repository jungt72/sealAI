"""Versioned tenant-bound HMAC references for MAT-GOV-03B."""

from __future__ import annotations

import hashlib
import hmac
import json
import re

from sealai_v2.core.material_shadow import ShadowErrorCode, ShadowContractError


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$", re.ASCII)


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
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
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

    def digest(self, value: str, *, key_id: str | None = None) -> str:
        selected = key_id or self.active_key_id
        key = self._keys.get(selected)
        if key is None:
            raise ShadowContractError(
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE, "unknown hmac_key_id"
            )
        if type(value) is not str or not value:
            raise ValueError("HMAC input must be a non-empty string")
        return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def contains(self, key_id: str) -> bool:
        return key_id in self._keys

    def references(self, value: str) -> tuple[tuple[str, str], ...]:
        """Return deterministic key-versioned references without exposing keys."""

        return tuple(
            (key_id, self.digest(value, key_id=key_id)) for key_id in sorted(self._keys)
        )
