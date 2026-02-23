# 📁 backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

* prüft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen für Endpoints (HTTP & WS)
* WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Optional

from fastapi import Depends, HTTPException, WebSocket, status, Header

from app.core.config import settings              # <-- korrekter Pfad!
import app.services.auth.token as auth_token
from app.langgraph_v2.contracts import error_detail


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RequestUser:
    user_id: str
    username: str
    sub: str
    roles: list[str]
    scopes: list[str] = field(default_factory=list)
    tenant_id: Optional[str] = None


def verify_access_token(token: str) -> dict:
    return auth_token.verify_access_token(token)


def _resolve_user_id(payload: dict) -> str:
    claim = (os.getenv("AUTH_USER_ID_CLAIM") or "sub").strip()
    value = payload.get(claim)
    if value is None or value == "":
        value = payload.get("preferred_username") or payload.get("email") or payload.get("sub")
        if value is None or value == "":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_detail("missing_user_id_claim", claim=claim),
            )
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


def _resolve_tenant_id(payload: dict) -> Optional[str]:
    claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()
    value = payload.get(claim)
    if value is not None and str(value).strip():
        return str(value).strip()
    return None


def _extract_scopes(payload: dict) -> list[str]:
    scopes: set[str] = set()
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str):
        for scope in raw_scope.replace(",", " ").split():
            scope = scope.strip()
            if scope:
                scopes.add(scope)
    raw_scp = payload.get("scp")
    if isinstance(raw_scp, str):
        for scope in raw_scp.replace(",", " ").split():
            scope = scope.strip()
            if scope:
                scopes.add(scope)
    elif isinstance(raw_scp, list):
        for scope in raw_scp:
            scope_str = str(scope).strip()
            if scope_str:
                scopes.add(scope_str)

    # Some Keycloak setups encode fine-grained privileges as roles.
    # Keep those visible as effective scopes for authorization gates.
    for role in _extract_roles(payload):
        if role.startswith("mcp:"):
            scopes.add(role)
    return sorted(scopes)


def canonical_user_id(user: RequestUser) -> str:
    """Return the canonical user id for scoping (claim-based preferred)."""
    return user.user_id or user.sub


async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = Header(default=None),
) -> RequestUser:
    """
    Liefert ein RequestUser-Objekt aus dem gültigen JWT,
    sonst → 401 UNAUTHORIZED.
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
    roles = _extract_roles(payload)
    scopes = _extract_scopes(payload)
    tenant_id = _resolve_tenant_id(payload)
    return RequestUser(user_id=user_id, username=username, sub=sub, roles=roles, scopes=scopes, tenant_id=tenant_id)


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency – für Chat-Streaming
#    (unterstützt Header *oder* Query-Parameter ?token=/ ?access_token=)
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> RequestUser:
    """
    Prüft beim WS-Handshake das Access Token.
    Bevorzugt `Authorization: Bearer <token>`, fällt aber auf Query-Parameter
    `?token=` oder `?access_token=` zurück (praktisch, da Browser-WS keine
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
    roles = _extract_roles(payload)
    scopes = _extract_scopes(payload)
    tenant_id = _resolve_tenant_id(payload)
    return RequestUser(user_id=user_id, username=username, sub=sub, roles=roles, scopes=scopes, tenant_id=tenant_id)
