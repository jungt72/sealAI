# ???? backend/app/services/auth/dependencies.py
"""
Auth-Dependencies f??r FastAPI-/WebSocket-Endpoints.

* pr??ft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen f??r Endpoints (HTTP & WS)
* WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re

from fastapi import Depends, HTTPException, WebSocket, status, Header

from app.core.config import settings              # <-- korrekter Pfad!
import app.services.auth.token as auth_token
from app.langgraph_v2.contracts import error_detail

# STRICT TENANT VALIDATION Regex
# Allow standard alphanumeric, dashes, underscores. Min 3 chars to prevent "a"/"id" etc abuse.
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")

# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency ??? f??r normale FastAPI-Routes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RequestUser:
    user_id: str
    username: str
    sub: str
    roles: list[str]
    tenant_id: str | None = None


logger = logging.getLogger(__name__)


def verify_access_token(token: str) -> dict:
    return auth_token.verify_access_token(token)


def _resolve_user_id(payload: dict) -> str:
    claim = (os.getenv("AUTH_USER_ID_CLAIM") or "sub").strip()
    value = payload.get(claim)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("missing_user_id_claim", claim=claim),
        )
    return str(value)


def _resolve_tenant_id(payload: dict) -> str | None:
    claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()
    value = payload.get(claim)
    if value is None or value == "":
        return None
    return str(value)


def _resolve_username(payload: dict) -> str:
    value = payload.get("preferred_username") or payload.get("email") or payload.get("sub")
    return str(value) if value else "anonymous"


def _extract_roles(payload: dict) -> list[str]:
    roles: set[str] = set()
    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        for role in realm_access.get("roles", []) or []:
            if role:
                roles.add(str(role))
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for entry in resource_access.values():
            if not isinstance(entry, dict):
                continue
            for role in entry.get("roles", []) or []:
                if role:
                    roles.add(str(role))
    return sorted(roles)


def canonical_user_id(user: RequestUser) -> str:
    """Return the canonical user id for scoping (claim-based preferred)."""
    return user.user_id or user.sub

def validate_tenant_id(tenant_id: str) -> str:
    """
    Validate tenant_id format to prevent injection attacks.
    Allows: Alphanumeric, hyphen, underscore. Length: 3-64.
    """
    cleaned = tenant_id.strip()
    if not TENANT_ID_PATTERN.match(cleaned):
        logger.warning("invalid_tenant_id_format", extra={"clean": cleaned[:10]})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("invalid_tenant", message="Tenant ID format invalid."),
        )
    return cleaned

def canonical_tenant_id(user: RequestUser) -> str:
    """
    Return the canonical tenant id for scoping (claim preferred).
    STRICT MODE: If tenant_id is missing, raise 403 unless ALLOW_TENANT_FALLBACK=1.
    """
    if user.tenant_id:
        return validate_tenant_id(user.tenant_id)

    # Fallback Logic (Migration only)
    allow_fallback = os.getenv("ALLOW_TENANT_FALLBACK") == "1"
    if allow_fallback:
        fallback = user.user_id or user.sub
        logger.warning(
            "tenant_id_claim_missing_fallback_active",
            extra={"user_id": user.user_id, "sub": user.sub},
        )
        # Fallback might be raw user ID which might not strictly match tenant structure,
        # but we validate it anyway as a defense measure for now.
        try:
             return validate_tenant_id(fallback)
        except HTTPException:
             # If fallback is allowed, failing here is strict defense.
             raise
             
    # Strict Mode Failure
    logger.error(
        "tenant_id_claim_missing_strict",
        extra={"user_id": user.user_id, "sub": user.sub},
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("missing_tenant", message="Tenant ID claim is mandatory."),
    )


async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = Header(default=None),
) -> RequestUser:
    """
    Liefert ein RequestUser-Objekt aus dem g??ltigen JWT,
    sonst ??? 401 UNAUTHORIZED.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ung??ltig",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = verify_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    user_id = _resolve_user_id(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    tenant_id = _resolve_tenant_id(payload)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, username=username, sub=sub, roles=roles, tenant_id=tenant_id)


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency ??? f??r Chat-Streaming
#    (unterst??tzt Header *oder* Query-Parameter ?token=/ ?access_token=)
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> RequestUser:
    """
    Pr??ft beim WS-Handshake das Access Token.
    Bevorzugt `Authorization: Bearer <token>`, f??llt aber auf Query-Parameter
    `?token=` oder `?access_token=` zur??ck (praktisch, da Browser-WS keine
    Custom-Header setzen kann).
    """
    # 1) Versuche Authorization-Header
    auth_header = websocket.headers.get("Authorization", "")
    token: str | None = None
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    # 2) Fallback: Query-Parameter (z. B. ws://.../ws?token=xxx)
    if not token:
        qp = websocket.query_params
        token = qp.get("token") or qp.get("access_token")

    if not token:
        await websocket.close(code=1008)  # Policy violation
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kein Token gefunden (weder Authorization-Header noch Query-Param).",
        )

    try:
        payload = verify_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    user_id = _resolve_user_id(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    tenant_id = _resolve_tenant_id(payload)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, username=username, sub=sub, roles=roles, tenant_id=tenant_id)
