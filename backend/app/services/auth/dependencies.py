# » backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

- prüft Bearer-Token (Keycloak / OIDC)
- liefert User/Scopes für Endpoints (HTTP & WS)
- WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=

Wichtige Ziele:
- tenant_id sauber aus Claims/Groups auflösen
- tenant_id strikt validieren (Fail closed), optionaler Fallback nur per ENV
- helper für konsistente Scope-ID (tenant:user)
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re

from fastapi import Header, HTTPException, WebSocket, status

from app.langgraph_v2.contracts import error_detail
from app.services.auth.scope import build_scope_id
import app.services.auth.token as auth_token

logger = logging.getLogger(__name__)

# STRICT TENANT VALIDATION Regex
# Allow standard alphanumeric, dashes, underscores. Min 3 chars to prevent "a"/"id" abuse.
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RequestUser:
    user_id: str
    username: str
    sub: str
    roles: list[str]
    tenant_id: str | None = None


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


def resolve_tenant_id_from_claims(payload: dict) -> str | None:
    """
    Resolve tenant_id from direct claims ('tenant_id', 'tenantID')
    OR from 'groups' claim (e.g. '/tenant-1' -> 'tenant-1').

    Strategy:
    1) Direct claim wins.
    2) 'groups' list is checked:
       - Strip leading '/' and whitespace.
       - If starts with 'tenant-': result is the whole string (e.g. 'tenant-1')
       - If starts with 'tenant:': result is split (e.g. 'tenant:1' -> '1')
    3) If multiple tenant groups are found -> FAIL CLOSED (return None).
    """
    # 1) Direct claim
    direct = payload.get("tenant_id") or payload.get("tenantID")
    if direct and isinstance(direct, str) and direct.strip():
        return direct.strip()

    # 2) Groups claim
    groups = payload.get("groups")
    if not groups:
        return None

    if isinstance(groups, str):
        groups = [groups]
    if not isinstance(groups, list):
        return None

    candidates: list[str] = []
    for g in groups:
        if not isinstance(g, str):
            continue
        clean = g.strip().lstrip("/")
        if not clean:
            continue

        if clean.startswith("tenant-"):
            candidates.append(clean)
        elif clean.startswith("tenant:"):
            parts = clean.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                candidates.append(parts[1].strip())

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        # Fail closed on ambiguity
        logger.warning(
            "ambiguous_tenant_groups",
            extra={"candidates": candidates, "sub": payload.get("sub")},
        )
        return None

    return None


def _resolve_tenant_id(payload: dict) -> str | None:
    # Prefer helper (claims + groups)
    found = resolve_tenant_id_from_claims(payload)
    if found:
        return found

    # Fallback to configured claim check (legacy/env override)
    claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()

    # resolve_tenant_id_from_claims already checked 'tenant_id' and 'tenantID'.
    if claim not in ("tenant_id", "tenantID"):
        value = payload.get(claim)
        if value and isinstance(value, str) and value.strip():
            return value.strip()

    return None


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
    """Canonical user id for scoping (claim-based preferred)."""
    return user.user_id or user.sub


def validate_tenant_id(tenant_id: str) -> str:
    """
    Validate tenant_id format to prevent injection attacks.
    Allows: Alphanumeric, hyphen, underscore. Length: 3-64.
    """
    cleaned = tenant_id.strip()
    if not TENANT_ID_PATTERN.match(cleaned):
        logger.warning("invalid_tenant_id_format", extra={"clean": cleaned[:16]})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("invalid_tenant", message="Tenant ID format invalid."),
        )
    return cleaned


def canonical_tenant_id(user: RequestUser) -> str:
    """
    Canonical tenant id for scoping.

    STRICT MODE:
      - If tenant_id is missing, raise 403 unless ALLOW_TENANT_FALLBACK=1.
    """
    if user.tenant_id:
        return validate_tenant_id(user.tenant_id)

    allow_fallback = os.getenv("ALLOW_TENANT_FALLBACK") == "1"
    if allow_fallback:
        fallback = user.user_id or user.sub
        logger.warning(
            "tenant_id_claim_missing_fallback_active",
            extra={"user_id": user.user_id, "sub": user.sub},
        )
        return validate_tenant_id(fallback)

    logger.error(
        "tenant_id_claim_missing_strict",
        extra={"user_id": user.user_id, "sub": user.sub},
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("missing_tenant", message="Tenant ID claim is mandatory."),
    )


def canonical_scope_id(user: RequestUser) -> str:
    """
    Stable scope-id for multi-tenant isolation: "{tenant}:{user}".
    Use this for Redis keys, SSE channels, etc.
    """
    tenant = canonical_tenant_id(user)
    uid = canonical_user_id(user)
    return build_scope_id(tenant_id=tenant, user_id=uid)


async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = Header(default=None),
) -> RequestUser:
    """
    Liefert ein RequestUser-Objekt aus dem gültigen JWT,
    sonst -> 401 UNAUTHORIZED.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
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

    return RequestUser(
        user_id=user_id,
        username=username,
        sub=sub,
        roles=roles,
        tenant_id=tenant_id,
    )


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency – für Chat-Streaming
#    (unterstützt Header oder Query-Parameter ?token= / ?access_token=)
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> RequestUser:
    """
    Prüft beim WS-Handshake das Access Token.
    Bevorzugt `Authorization: Bearer <token>`, fällt aber auf Query-Parameter
    `?token=` oder `?access_token=` zurück (praktisch, da Browser-WS keine
    Custom-Header setzen kann).
    """
    auth_header = websocket.headers.get("Authorization", "")
    token: str | None = None

    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

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

    return RequestUser(
        user_id=user_id,
        username=username,
        sub=sub,
        roles=roles,
        tenant_id=tenant_id,
    )
