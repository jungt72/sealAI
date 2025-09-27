# NOTE: This file has been adapted to improve WebSocket token handling.
# The original code expected JWTs only in the Authorization header or the
# `?token=` query parameter. Browsers cannot set arbitrary headers when
# establishing a WebSocket connection, so clients often pass the JWT in the
# `Sec-WebSocket-Protocol` field. The new implementation extracts tokens
# from Authorization headers, query parameters and the WebSocket subprotocol.

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
    """
    Parse a comma‑separated environment variable into a list of strings.

    Empty or unset variables return an empty list. Items are stripped of
    whitespace.
    """
    raw = (os.getenv(env) or "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def _norm_url(u: str) -> str:
    """
    Normalize URLs for strict comparison by lowercasing the scheme and host,
    and stripping any trailing slash. If parsing fails, returns the original
    value in lowercase without a trailing slash.
    """
    if not u:
        return ""
    try:
        p = urlparse.urlparse(u.strip())
        scheme = (p.scheme or "https").lower()
        host = (p.hostname or "").lower()
        port = f":{p.port}" if p.port else ""
        path = (p.path or "").rstrip("/")
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return u.strip().rstrip("/").lower()


REALM_URL = os.getenv("KEYCLOAK_REALM_URL", "https://auth.sealai.net/realms/sealAI")
ISSUER_ENV = os.getenv("KEYCLOAK_ISSUER", REALM_URL)
ALLOWED_ISSUERS = {ISSUER_ENV, REALM_URL, *_csv("KEYCLOAK_ALLOWED_ISSUERS")}
ALLOWED_ISSUERS_NORM = {_norm_url(x) for x in ALLOWED_ISSUERS if x}

JWKS_URL = (
    os.getenv("KEYCLOAK_JWKS_URL")
    or f"{_norm_url(ISSUER_ENV)}/protocol/openid-connect/certs"
)

ALLOWED_AUDIENCES = set(_csv("ALLOWED_AUDIENCES") or ["account", "nextauth", "sealai-backend-api"])

JWKS_TTL_SEC = int(os.getenv("JWKS_TTL_SEC", "600"))
CLOCK_SKEW = int(os.getenv("WS_CLOCK_SKEW_LEEWAY", "120"))

# ---- JWKS cache with TTL -----------------------------------------------------

_JWKS_CACHE = {"data": None, "ts": 0.0}


def _get_jwks_cached() -> dict:
    """
    Fetch the JSON Web Key Set (JWKS) used to verify JWT signatures. A simple
    in‑memory cache with a TTL avoids repeatedly calling the JWKS endpoint.
    """
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


def _jwks_clear() -> None:
    """
    Clear the JWKS cache. Useful for forcing a refresh when the expected
    signing key is not present.
    """
    _JWKS_CACHE["data"] = None
    _JWKS_CACHE["ts"] = 0.0


def _find_key(kid: str) -> Optional[dict]:
    """
    Locate the public key with the given `kid` in the JWKS. If not found on
    the first attempt, forces a cache refresh and tries again.
    """
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
    """
    Verify an RS256 JWT. Validates the signature, expiry and not‑before
    timestamps, issuer and audience/authorized party claims. Raises a
    `ValueError` with descriptive text on any failure.
    """
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
    try:
        signing_input, signature = token.rsplit(".", 1)
    except ValueError:
        raise ValueError("token missing signature part")
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


def extract_bearer_or_query_token(websocket: WebSocket) -> Optional[str]:
    """
    Extract a JWT from a WebSocket request.

    The token can be provided in three different ways:

    1. As an HTTP `Authorization` header with the scheme `Bearer`.
    2. As a `token` query parameter on the WebSocket URL.
    3. As part of the `Sec-WebSocket-Protocol` header. When a browser
       establishes a WebSocket it may send one or more subprotocols.
       If the first subprotocol is `bearer`, `jwt` or `token`, the next
       value is assumed to be the JWT. Alternatively, if there is only
       a single subprotocol and it contains dots (e.g. typical for JWTs), it
       is treated as the token directly.

    Returns the extracted token, or `None` if no token was found.
    """
    # 1) Authorization header
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    # 2) Query parameter
    try:
        token = websocket.query_params.get("token")  # type: ignore[assignment]
    except Exception:
        token = None
    if token:
        token = str(token).strip()
        if token:
            return token

    # 3) Sec-WebSocket-Protocol header
    sp = websocket.headers.get("sec-websocket-protocol") or websocket.headers.get("Sec-WebSocket-Protocol")
    if sp:
        # Split on commas into individual protocols
        protocols = [p.strip() for p in sp.split(",") if p.strip()]
        if protocols:
            first = protocols[0].lower()
            # explicit scheme indicates next entry holds the token
            if first in {"bearer", "jwt", "token"}:
                if len(protocols) > 1:
                    return protocols[1]
            # single subprotocol that looks like a JWT (contains dot separators)
            if len(protocols) == 1 and "." in protocols[0]:
                return protocols[0]
    return None


def _truthy(v: Optional[str]) -> bool:
    """
    Convert various string representations of truth to a boolean. Recognises
    `1`, `true`, `yes` and `on` (case‑insensitive). Any other value
    (including `None`) yields `False`.
    """
    if v is None:
        return False
    v = str(v).strip().strip("'\"").lower()
    return v in ("1", "true", "yes", "on")


def _allowed_origins_set() -> set[str]:
    """
    Parse the `ALLOWED_ORIGIN` environment variable into a set of origin strings.
    Multiple entries are comma‑separated. Empty values are ignored.
    """
    raw = (os.getenv("ALLOWED_ORIGIN", "") or "").strip().strip("'\"")
    return {o.strip() for o in raw.split(",") if o.strip()}


def check_origin_allowed(origin: Optional[str]) -> Tuple[bool, str]:
    """
    Determine if a request's origin is allowed to connect to the WebSocket.

    Returns a tuple of `(allowed, reason)` where `allowed` is a boolean and
    `reason` is a human‑readable explanation. The logic is driven by
    environment variables:

    * `ALLOW_WS_ORIGIN_ANY` set to a truthy value bypasses all checks.
    * `WS_REQUIRE_ORIGIN` forces an `Origin` header to be present.
    * `ALLOWED_ORIGIN` contains a comma‑separated list of permitted origins.
      A wildcard `*` or `any` allows any origin.
    """
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
    """
    Validate that the provided JWT payload authorises the given origin. The
    optional claim `allowed-origins` may be present on the token. If
    `WS_ENFORCE_TOKEN_ORIGIN` is not set, the check is skipped. Returns a
    tuple of `(allowed, reason)`.
    """
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
    """
    Verify the JWT and return its payload. Raises an exception on any
    validation failure. Logging at WARNING level captures the exception for
    easier troubleshooting.
    """
    try:
        return _verify_rs256(token)
    except Exception as e:
        logger.warning("JWT verify failed: %s", e)
        raise


async def guard_websocket(websocket: WebSocket) -> dict:
    """
    Full WebSocket guard. Validates the request origin and extracts and
    verifies the bearer token. On failure an exception is raised; callers are
    responsible for closing the websocket when handling the error.

    On success the verified JWT payload is attached to the `websocket.scope` as
    `'user'` and returned to the caller.
    """
    origin = websocket.headers.get("origin")

    ok, _ = check_origin_allowed(origin)
    if not ok:
        raise RuntimeError("forbidden origin")

    token = extract_bearer_or_query_token(websocket)
    if not token:
        raise RuntimeError("missing bearer token")

    try:
        payload = verify_token_or_raise(token)
    except Exception:
        raise

    ok2, _ = token_allows_origin(payload, origin)
    if not ok2:
        raise RuntimeError("token origin mismatch")

    websocket.scope["user"] = payload
    return payload
