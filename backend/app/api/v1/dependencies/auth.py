import os
import time
import logging
from typing import Optional, Tuple

import httpx
from jose import jwt, jwk
from jose.utils import base64url_decode
from fastapi import WebSocket, Request, HTTPException, status

logger = logging.getLogger("auth")

REALM_URL = os.getenv("KEYCLOAK_REALM_URL", "https://auth.sealai.net/realms/sealAI")
JWKS_URL = f"{REALM_URL}/protocol/openid-connect/certs"
ISSUER = REALM_URL
ALLOWED_AUDIENCES = set(
    (os.getenv("ALLOWED_AUDIENCES") or "account,nextauth,sealai-backend-api").split(",")
)

from functools import lru_cache

@lru_cache(maxsize=1)
def _get_jwks_cached() -> dict:
    logger.info("Fetching JWKS from %s", JWKS_URL)
    with httpx.Client(timeout=10.0) as client:
        r = client.get(JWKS_URL)
        r.raise_for_status()
        return r.json()

def _find_key(kid: str) -> Optional[dict]:
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None

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
        _get_jwks_cached.cache_clear()
        key_dict = _find_key(kid)
        if not key_dict:
            raise ValueError("jwks key not found for kid")

    signing_input, signature = token.rsplit(".", 1)
    signature_bytes = base64url_decode(signature.encode())
    public_key = jwk.construct(key_dict)

    if not public_key.verify(signing_input.encode(), signature_bytes):
        raise ValueError("signature verification failed")

    now = int(time.time())
    exp = int(payload.get("exp", 0))
    nbf = int(payload.get("nbf", 0))
    iss = payload.get("iss")

    if not iss or iss != ISSUER:
        raise ValueError(f"invalid issuer: {iss}")
    if nbf and now < nbf:
        raise ValueError("token not yet valid (nbf)")
    if exp and now >= exp:
        raise ValueError("token expired")

    aud = payload.get("aud")
    if isinstance(aud, str):
        aud_ok = aud in ALLOWED_AUDIENCES
    elif isinstance(aud, (list, tuple, set)):
        aud_ok = any(a in ALLOWED_AUDIENCES for a in aud)
    else:
        aud_ok = False
    if not aud_ok:
        azp = payload.get("azp")
        client_id = payload.get("client_id")
        if not ((azp in ALLOWED_AUDIENCES) or (client_id in ALLOWED_AUDIENCES)):
            raise ValueError(f"aud not allowed: {aud}")

    return payload

def extract_bearer_or_query_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = websocket.query_params.get("token")
    if token:
        return token.strip()
    return None

def verify_token_or_raise(token: str) -> dict:
    try:
        return _verify_rs256(token)
    except Exception as e:
        logger.warning("JWT verify failed: %s", e)
        raise

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
    # Optional stricter Check, steuerbar via WS_ENFORCE_TOKEN_ORIGIN (default 0)
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

def require_http_bearer(request: Request) -> dict:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        return verify_token_or_raise(token)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}")

async def guard_websocket(websocket: WebSocket) -> dict:
    origin = websocket.headers.get("origin")

    # 1) Origin-Policy
    ok, why = check_origin_allowed(origin)
    if not ok:
        await websocket.close(code=4403)
        raise RuntimeError(f"forbidden origin: {why}")

    # 2) Token Pflicht
    token = extract_bearer_or_query_token(websocket)
    if not token:
        await websocket.close(code=4401)
        raise RuntimeError("missing bearer token")

    # 3) Token prüfen
    try:
        payload = verify_token_or_raise(token)
    except Exception:
        await websocket.close(code=4401)
        raise

    # 4) Optional: Token-Origin-Claim erzwingen
    ok2, why2 = token_allows_origin(payload, origin)
    if not ok2:
        await websocket.close(code=4403)
        raise RuntimeError(f"token origin mismatch: {why2}")

    return payload
