# backend/app/services/auth/token.py
"""
Token-Utilities
===============

Verifiziert Keycloak-JWTs für das Backend (REST & WebSocket).
Mit erweitertem Diagnose-Logging für Debug-Zwecke via Logger.
"""

from __future__ import annotations

import functools
from typing import Any, Final

import httpx
from jose import JWTError, jwt
import logging

log = logging.getLogger("uvicorn.error")

# --------------------------------------------------------------------------- #
#   Parameter – an deine Umgebung anpassen
# --------------------------------------------------------------------------- #

REALM_ISSUER: Final[str] = "https://sealai.net/realms/sealAI"
JWKS_URL:     Final[str] = f"{REALM_ISSUER}/protocol/openid-connect/certs"

# *Alle* Audiences, die wir akzeptieren …
ALLOWED_AUDS: Final[set[str]] = {"nextauth", "sealai-backend-api"}

# --------------------------------------------------------------------------- #
#   interner JWKS-Cache
# --------------------------------------------------------------------------- #

@functools.lru_cache(maxsize=1)
def _get_jwks() -> dict[str, Any]:
    resp = httpx.get(JWKS_URL, timeout=5.0, verify=False)
    resp.raise_for_status()
    return resp.json()


def _get_key(kid: str) -> dict[str, str]:
    for key in _get_jwks()["keys"]:
        if key["kid"] == kid:
            return key
    raise JWTError(f"kid {kid!r} not found in JWKS")

# --------------------------------------------------------------------------- #
#   Public API
# --------------------------------------------------------------------------- #

def verify_access_token(token: str) -> dict[str, Any]:
    """
    * Gibt den vollständigen Claim-Dict zurück, wenn alles passt
    * Löst **ValueError** aus, wenn der Token ungültig ist
    * Gibt bei jedem Schritt detailliertes Diagnose-Logging via Logger aus
    """
    try:
        header = jwt.get_unverified_header(token)
        log.warning("### JWT HEADER: %r", header)
        key    = _get_key(header["kid"])
        log.warning("### JWT KEY: %r", key)

        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[header["alg"]],
            issuer=REALM_ISSUER,
            options={
                "verify_aud": False
            },
        )

        log.warning("### JWT CLAIMS: %r", claims)

        aud_ok = False

        # 1) preferierter Claim „azp“
        if claims.get("azp") in ALLOWED_AUDS:
            aud_ok = True

        # 2) OIDC-Standard-Claim „aud“
        aud = claims.get("aud")
        if isinstance(aud, str) and aud in ALLOWED_AUDS:
            aud_ok = True
        elif isinstance(aud, list) and any(a in ALLOWED_AUDS for a in aud):
            aud_ok = True

        if not aud_ok:
            raise JWTError(f"audience not allowed ({aud!r})")

        return claims

    except Exception as exc:
        log.error("### JWT ERROR: %r", exc)
        raise ValueError(str(exc)) from exc
