# 📁 backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

* prüft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen für Endpoints (HTTP & WS)
* WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=
"""

from __future__ import annotations

from dataclasses import dataclass
import os

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
    tenant_id: str
    username: str
    sub: str
    roles: list[str]


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


def _resolve_tenant_id(payload: dict) -> str:
    claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()
    value = payload.get(claim)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("missing_tenant_id_claim", claim=claim),
        )
    return str(value)


def _resolve_tenant_id_strict(payload: dict) -> str:
    claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()
    value = payload.get(claim)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("tenant_id_claim_missing_strict", claim=claim),
        )
    return str(value)


def _tenant_invalid_detail(*, tenant_id: str, user_id: str, sub: str) -> dict:
    detail = error_detail("tenant_id_invalid")
    if os.getenv("AUTH_DEBUG") == "1":
        detail.update(
            {
                "reason": "tenant_equals_sub",
                "tenant_id": tenant_id,
                "user_id": user_id,
                "sub": sub,
            }
        )
    return detail


def _ensure_canonical_tenant_id(*, tenant_id: str, user_id: str, sub: str) -> None:
    if tenant_id == user_id or tenant_id == sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_tenant_invalid_detail(tenant_id=tenant_id, user_id=user_id, sub=sub),
        )


def _resolve_username(payload: dict) -> str:
    value = payload.get("preferred_username") or payload.get("email") or payload.get("sub")
    return str(value) if value else "anonymous"


def _extract_roles(payload: dict) -> list[str]:
    roles: set[str] = set()
    def _add_roles(values: object) -> None:
        if not values:
            return
        for role in values or []:
            if role:
                roles.add(str(role))

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        _add_roles(realm_access.get("roles", []))
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        client_candidates = []
        for candidate in (
            payload.get("azp"),
            payload.get("client_id"),
            settings.keycloak_client_id,
            settings.keycloak_expected_azp,
        ):
            if candidate:
                client_candidates.append(str(candidate))
        for client_id in dict.fromkeys(client_candidates):
            entry = resource_access.get(client_id)
            if isinstance(entry, dict):
                _add_roles(entry.get("roles", []))
        for entry in resource_access.values():
            if not isinstance(entry, dict):
                continue
            _add_roles(entry.get("roles", []))
    return sorted(roles)


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
    tenant_id = _resolve_tenant_id(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, tenant_id=tenant_id, username=username, sub=sub, roles=roles)


async def get_current_request_user_strict_tenant(
    authorization: str | None = Header(default=None),
) -> RequestUser:
    """
    Strict variant: require tenant claim and reject tenant_id == user/sub.
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
    tenant_id = _resolve_tenant_id_strict(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    _ensure_canonical_tenant_id(tenant_id=tenant_id, user_id=user_id, sub=sub)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, tenant_id=tenant_id, username=username, sub=sub, roles=roles)


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
    tenant_id = _resolve_tenant_id(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, tenant_id=tenant_id, username=username, sub=sub, roles=roles)


async def get_current_ws_user_strict_tenant(websocket: WebSocket) -> RequestUser:
    """
    Strict WS variant: require tenant claim and reject tenant_id == user/sub.
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
    tenant_id = _resolve_tenant_id_strict(payload)
    username = _resolve_username(payload)
    sub = str(payload.get("sub") or user_id)
    _ensure_canonical_tenant_id(tenant_id=tenant_id, user_id=user_id, sub=sub)
    roles = _extract_roles(payload)
    return RequestUser(user_id=user_id, tenant_id=tenant_id, username=username, sub=sub, roles=roles)
