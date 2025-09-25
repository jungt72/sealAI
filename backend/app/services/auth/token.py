"""
Token-Utilities
===============
Verifiziert Keycloak-JWTs für das Backend (REST & WebSocket).
Logging reduziert (keine sensiblen Daten), Algorithmen strikt auf RS256.
"""

from __future__ import annotations
from app.core.config import settings
import functools
from typing import Any, Final
import httpx
from jose import jwt, JWTError
import logging
import base64
import re
import json

log = logging.getLogger("uvicorn.error")

REALM_ISSUER: Final[str] = settings.backend_keycloak_issuer
JWKS_URL: Final[str] = settings.keycloak_jwks_url
ALLOWED_AUDS: Final[set[str]] = {"nextauth", "sealai-backend-api"}
ALLOWED_ALGS: Final[tuple[str, ...]] = ("RS256",)  # ✅ fixiert

@functools.lru_cache(maxsize=1)
def _get_jwks() -> dict[str, Any]:
    resp = httpx.get(JWKS_URL, timeout=5.0, verify=True)
    resp.raise_for_status()
    return resp.json()

def _get_key(kid: str) -> dict[str, Any]:
    for key in _get_jwks()["keys"]:
        if key["kid"] == kid:
            return key
    raise JWTError(f"kid {kid!r} not found in JWKS")

def _jwk_to_pem(jwk: dict[str, Any]) -> str:
    x5c = jwk.get("x5c")
    if not x5c:
        raise JWTError("x5c field missing in JWKS")
    cert = x5c[0]
    cert_str = "-----BEGIN CERTIFICATE-----\n"
    cert_str += "\n".join(cert[i:i+64] for i in range(0, len(cert), 64))
    cert_str += "\n-----END CERTIFICATE-----\n"
    return cert_str

def _safe_get_unverified_header(token: str) -> dict:
    try:
        header_b64 = token.split(".")[0]
        header_b64 = re.sub(r'[^A-Za-z0-9_\-]', '', header_b64)
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

        claims: dict[str, Any] = jwt.decode(
            token,
            public_key_pem,
            algorithms=list(ALLOWED_ALGS),  # ✅ strikt
            issuer=REALM_ISSUER,
            options={"verify_aud": False},  # aud separat prüfen
        )

        # Audience/Client-Checks
        aud = claims.get("aud")
        aud_ok = (
            (isinstance(aud, str)  and aud in ALLOWED_AUDS)
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
