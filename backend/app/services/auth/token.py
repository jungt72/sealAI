"""
Token-Utilities
===============
Verifiziert Keycloak-JWTs für das Backend (REST & WebSocket).
Logging reduziert (keine sensiblen Daten), Algorithmen strikt auf RS256.
"""

from __future__ import annotations

from app.core.config import settings
from typing import Any, Final
import os
import time
import httpx
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
import logging
import base64
import re
import json

log = logging.getLogger("uvicorn.error")

REALM_ISSUER: Final[str] = settings.backend_keycloak_issuer
JWKS_URL: Final[str] = settings.keycloak_jwks_url


def _build_allowed_auds() -> set[str]:
    candidates = {
        settings.keycloak_client_id,
        settings.keycloak_expected_azp,
        "nextauth",
        "sealai-backend-api",
        "sealai-cli",
    }
    return {value for value in candidates if value}


ALLOWED_AUDS: Final[set[str]] = _build_allowed_auds()
ALLOWED_ALGS: Final[tuple[str, ...]] = ("RS256",)  # ✅ fixiert
JWKS_TTL_SEC: Final[int] = int(os.getenv("KEYCLOAK_JWKS_TTL_SEC", "600"))
JWT_LEEWAY_SEC: Final[int] = int(os.getenv("KEYCLOAK_JWT_LEEWAY_SEC", "60"))

_JWKS_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}


def _get_jwks_cached(force_refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    if (
        not force_refresh
        and _JWKS_CACHE["data"] is not None
        and now - _JWKS_CACHE["ts"] < JWKS_TTL_SEC
    ):
        return _JWKS_CACHE["data"]
    resp = httpx.get(JWKS_URL, timeout=5.0, verify=True)
    resp.raise_for_status()
    _JWKS_CACHE["data"] = resp.json()
    _JWKS_CACHE["ts"] = now
    return _JWKS_CACHE["data"]


def _get_key(kid: str) -> dict[str, Any]:
    if not kid:
        raise JWTError("missing_kid")
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    # refresh on kid-miss
    jwks = _get_jwks_cached(force_refresh=True)
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise JWTError(f"kid {kid!r} not found in JWKS")


def _jwk_to_pem(jwk: dict[str, Any]) -> str:
    x5c = jwk.get("x5c")
    if not x5c:
        raise JWTError("x5c field missing in JWKS")
    cert = x5c[0]
    cert_str = "-----BEGIN CERTIFICATE-----\n"
    cert_str += "\n".join(cert[i : i + 64] for i in range(0, len(cert), 64))
    cert_str += "\n-----END CERTIFICATE-----\n"
    return cert_str


def _safe_get_unverified_header(token: str) -> dict:
    try:
        header_b64 = token.split(".")[0]
        header_b64 = re.sub(r"[^A-Za-z0-9_\-]", "", header_b64)
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        return json.loads(decoded)
    except Exception as exc:
        log.debug("JWT header decode failed: %r", exc)
        raise JWTError("Header decode fail") from exc


def verify_access_token(token: str) -> dict[str, Any]:
    """
    * Gibt den vollständigen Claim-Dict zurück, wenn alles passt
    * Löst ValueError aus, wenn der Token ungültig ist
    """
    try:
        header = _safe_get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")

        if alg not in ALLOWED_ALGS:
            raise JWTError(f"unsupported alg {alg!r}; allowed={ALLOWED_ALGS}")

        jwk = _get_key(kid)
        public_key_pem = _jwk_to_pem(jwk)

        # python-jose: leeway MUST be provided inside `options`, not as kwarg.
        decode_options = {
            "verify_aud": False,  # aud separat prüfen
            "verify_exp": True,
            "verify_nbf": True,
            # Leeway/clock skew (seconds)
            "leeway": int(JWT_LEEWAY_SEC or 0),
        }

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                public_key_pem,
                algorithms=list(ALLOWED_ALGS),  # ✅ strikt
                issuer=REALM_ISSUER,
                options=decode_options,
            )
        except ExpiredSignatureError as exc:
            # normalize to a stable error token
            raise JWTError("token_expired") from exc
        except JWTError as exc:
            message = str(exc).lower()
            if "signature" in message:
                raise JWTError("invalid_signature") from exc
            raise

        # Audience/Client-Checks
        aud = claims.get("aud")
        aud_ok = (
            (isinstance(aud, str) and aud in ALLOWED_AUDS)
            or (isinstance(aud, list) and any(a in ALLOWED_AUDS for a in aud))
            or (claims.get("azp") in ALLOWED_AUDS)
            or (claims.get("client_id") in ALLOWED_AUDS)
        )
        if not aud_ok:
            raise JWTError(
                f"audience not allowed (aud={aud!r}, azp={claims.get('azp')!r}, client_id={claims.get('client_id')!r})"
            )

        # Minimal-log (kein PEM/keine Claims)
        log.debug("JWT verified (kid=%s, alg=%s, iss ok, aud ok)", kid, alg)
        return claims

    except Exception as exc:
        log.warning("JWT verify failed: %s", exc)
        raise ValueError(str(exc)) from exc
