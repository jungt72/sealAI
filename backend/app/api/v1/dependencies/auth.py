import os
import time
import logging
from typing import Optional, Tuple, Iterable
import urllib.parse as urlparse

import httpx
from jose import jwt, jwk
from jose.utils import base64url_decode
from fastapi import WebSocket

logger = logging.getLogger("auth")

# ---- Config / ENV ------------------------------------------------------------

def _csv(env: str) -> Iterable[str]:
    raw = (os.getenv(env) or "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]

def _norm_url(u: str) -> str:
    """Normalize for strict compare: lowercase scheme/host, strip trailing slash."""
    if not u:
        return ""
    try:
        p = urlparse.urlparse(u.strip())
        scheme = (p.scheme or "https").lower()
        host   = (p.hostname or "").lower()
        port   = f":{p.port}" if p.port else ""
        path   = (p.path or "").rstrip("/")
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return u.strip().rstrip("/").lower()

REALM_URL  = os.getenv("KEYCLOAK_REALM_URL", "https://auth.sealai.net/realms/sealAI")
ISSUER_ENV = os.getenv("KEYCLOAK_ISSUER", REALM_URL)
ALLOWED_ISSUERS = {ISSUER_ENV, REALM_URL, *_csv("KEYCLOAK_ALLOWED_ISSUERS")}
ALLOWED_ISSUERS_NORM = {_norm_url(x) for x in ALLOWED_ISSUERS if x}

JWKS_URL = (
    os.getenv("KEYCLOAK_JWKS_URL")
    or f"{_norm_url(ISSUER_ENV)}/protocol/openid-connect/certs"
)

ALLOWED_AUDIENCES = set(_csv("ALLOWED_AUDIENCES") or ["account", "nextauth", "sealai-backend-api"])

JWKS_TTL_SEC = int(os.getenv("JWKS_TTL_SEC", "600"))
CLOCK_SKEW   = int(os.getenv("WS_CLOCK_SKEW_LEEWAY", "120"))

# ---- JWKS cache with TTL -----------------------------------------------------

_JWKS_CACHE = {"data": None, "ts": 0.0}

def _get_jwks_cached() -> dict:
    now = time.time()
    if _JWKS_CACHE["data"] and (now - _JWKS_CACHE["ts"] < JWKS_TTL_SEC):
        return _JWKS_CACHE["data"]  # type: ignore[return-value]
    logger.info("Fetching JWKS from %s", JWKS_URL)
    with httpx.Client(timeout=10.0) as client:
        r = client.get(JWKS_URL)
        r.raise_for_status()
        _JWKS_CACHE["data"] = r.json()
        _JWKS_CACHE["ts"] = now
        return _JWKS_CACHE["data"]  # type: ignore[return-value]

def _jwks_clear():
    _JWKS_CACHE["data"] = None
    _JWKS_CACHE["ts"] = 0.0

def _find_key(kid: str) -> Optional[dict]:
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    # miss? refresh once
    _jwks_clear()
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None

# ---- Token verification ------------------------------------------------------

def _verify_rs256(token: str) -> dict:
    try:
        headers = jwt.get_unverified_header(token)
        payload = jwt.get_unverified_claims(token)
    except Exception as e:
        raise ValueError(f"invalid token format: {e}")

    kid = headers.get("kid")
    if not kid:
        raise ValueError("token header missing 'kid'")

    key_dict = _find_key(kid)
    if not key_dict:
        raise ValueError("jwks key not found for kid")

    # signature
    signing_input, signature = token.rsplit(".", 1)
    signature_bytes = base64url_decode(signature.encode())
    public_key = jwk.construct(key_dict)
    if not public_key.verify(signing_input.encode(), signature_bytes):
        raise ValueError("signature verification failed")

    # temporal claims (with skew)
    now = int(time.time())
    exp = int(payload.get("exp", 0) or 0)
    nbf = int(payload.get("nbf", 0) or 0)
    if nbf and now + CLOCK_SKEW < nbf:
        raise ValueError("token not yet valid (nbf)")
    if exp and now - CLOCK_SKEW >= exp:
        raise ValueError("token expired")

    # issuer (case/host normalized)
    iss = payload.get("iss")
    if _norm_url(iss or "") not in ALLOWED_ISSUERS_NORM:
        raise ValueError(f"invalid issuer: {iss}")

    # audience / azp fallback
    aud = payload.get("aud")
    aud_ok = False
    if isinstance(aud, str):
        aud_ok = aud in ALLOWED_AUDIENCES
    elif isinstance(aud, (list, tuple, set)):
        aud_ok = any(a in ALLOWED_AUDIENCES for a in aud)
    if not aud_ok:
        azp = payload.get("azp") or payload.get("client_id")
        if not azp or azp not in ALLOWED_AUDIENCES:
            raise ValueError(f"aud not allowed: {aud}")

    return payload

# ---- WS helpers --------------------------------------------------------------

from fastapi import WebSocket

def extract_bearer_or_query_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = websocket.query_params.get("token")
    if token:
        return token.strip()
    return None

def _truthy(v: Optional[str]) -> bool:
    if v is None:
        return False
    v = str(v).strip().strip('\'"').lower()
    return v in ("1", "true", "yes", "on")

def _allowed_origins_set() -> set[str]:
    raw = (os.getenv("ALLOWED_ORIGIN", "") or "").strip().strip('\'"')
    return {o.strip() for o in raw.split(",") if o.strip()}

def check_origin_allowed(origin: Optional[str]) -> Tuple[bool, str]:
    if _truthy(os.getenv("ALLOW_WS_ORIGIN_ANY", "0")):
        return True, "ALLOW_WS_ORIGIN_ANY=1"
    if not origin and not _truthy(os.getenv("WS_REQUIRE_ORIGIN", "0")):
        return True, "no Origin header (allowed)"
    if not origin:
        return False, "missing Origin header"
    allowed = _allowed_origins_set()
    if not allowed:
        return False, "ALLOWED_ORIGIN not configured"
    if "*" in allowed or "any" in allowed:
        return True, "ALLOWED_ORIGIN=*"
    if origin in allowed:
        return True, "origin ok"
    return False, f"origin '{origin}' not in {sorted(allowed)}"

def token_allows_origin(payload: dict, origin: Optional[str]) -> Tuple[bool, str]:
    if not _truthy(os.getenv("WS_ENFORCE_TOKEN_ORIGIN", "0")):
        return True, "token-origin check disabled"
    if not origin:
        return True, "skip claim check (no origin)"
    claim = payload.get("allowed-origins")
    if not claim:
        return True, "no allowed-origins claim; skipping"
    if isinstance(claim, list) and origin in claim:
        return True, "allowed-origins claim ok"
    return False, f"origin '{origin}' not in token allowed-origins"

def verify_token_or_raise(token: str) -> dict:
    try:
        return _verify_rs256(token)
    except Exception as e:
        logger.warning("JWT verify failed: %s", e)
        raise

async def guard_websocket(websocket: WebSocket) -> dict:
    origin = websocket.headers.get("origin")

    ok, _ = check_origin_allowed(origin)
    if not ok:
        await websocket.close(code=1008)
        raise RuntimeError("forbidden origin")

    token = extract_bearer_or_query_token(websocket)
    if not token:
        await websocket.close(code=1008)
        raise RuntimeError("missing bearer token")

    try:
        payload = verify_token_or_raise(token)
    except Exception:
        await websocket.close(code=1008)
        raise

    ok2, _ = token_allows_origin(payload, origin)
    if not ok2:
        await websocket.close(code=1008)
        raise RuntimeError("token origin mismatch")

    websocket.scope["user"] = payload
    return payload
