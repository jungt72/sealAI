# backend/app/services/auth/token.py
"""
Token-Utilities
===============
Verifiziert Keycloak-JWTs für das Backend (REST & WebSocket).
Mit erweitertem Diagnose-Logging für Debug-Zwecke via Logger.
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

log = logging.getLogger("uvicorn.error")

REALM_ISSUER: Final[str] = settings.backend_keycloak_issuer
JWKS_URL: Final[str] = settings.keycloak_jwks_url
ALLOWED_AUDS: Final[set[str]] = {"nextauth", "sealai-backend-api"}

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
    cert_str = "-----BEGIN CERTIFICATE-----\n"
    cert_str += "\n".join(x5c[0][i:i+64] for i in range(0, len(x5c[0]), 64))
    cert_str += "\n-----END CERTIFICATE-----\n"
    return cert_str

# --- Whitespace-toleranter, robuster JWT-Header-Decoder ---
def _safe_get_unverified_header(token: str) -> dict:
    try:
        header_b64 = token.split(".")[0]
        header_b64 = re.sub(r'[^A-Za-z0-9_\-]', '', header_b64)
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
        import json
        return json.loads(decoded)
    except Exception as exc:
        log.error("### JWT HEADER DECODE FAIL: %r", exc)
        raise JWTError("Header decode fail") from exc

def verify_access_token(token: str) -> dict[str, Any]:
    """
    * Gibt den vollständigen Claim-Dict zurück, wenn alles passt
    * Löst **ValueError** aus, wenn der Token ungültig ist
    * Gibt bei jedem Schritt detailliertes Diagnose-Logging via Logger aus
    """
    try:
        # NEU: Whitespace- und encoding-tolerant!
        header = _safe_get_unverified_header(token)
        log.warning("### JWT HEADER: %r", header)
        jwk    = _get_key(header["kid"])
        log.warning("### JWT KEY: %r", jwk)

        public_key_pem = _jwk_to_pem(jwk)
        log.warning("### JWT PUBLIC KEY PEM: %r", public_key_pem[:80] + "...")

        claims: dict[str, Any] = jwt.decode(
            token,
            public_key_pem,
            algorithms=[header["alg"]],
            issuer=REALM_ISSUER,
            options={"verify_aud": False},
        )
        log.warning("### JWT CLAIMS: %r", claims)

        # 1) OIDC-Standard-Claim "aud" (String oder Liste)
        aud = claims.get("aud")
        aud_ok = (
            (isinstance(aud, str) and aud in ALLOWED_AUDS)
            or (isinstance(aud, list) and any(a in ALLOWED_AUDS for a in aud))
        )
        # 2) Fallback Claim "azp"
        if not aud_ok and claims.get("azp") in ALLOWED_AUDS:
            aud_ok = True
        # 3) Service-Account via "client_id"
        if not aud_ok and claims.get("client_id") in ALLOWED_AUDS:
            aud_ok = True

        if not aud_ok:
            raise JWTError(f"audience not allowed (aud={aud!r}, azp={claims.get('azp')!r}, client_id={claims.get('client_id')!r})")

        return claims

    except Exception as exc:
        log.error("### JWT ERROR: %r", exc)
        raise ValueError(str(exc)) from exc
