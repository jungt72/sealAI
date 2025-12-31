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


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RequestUser:
    user_id: str
    username: str
    sub: str


def verify_access_token(token: str) -> dict:
    return auth_token.verify_access_token(token)


def _resolve_user_id(payload: dict) -> str:
    claim = (os.getenv("AUTH_USER_ID_CLAIM") or "preferred_username").strip().lower()
    if claim == "sub":
        value = payload.get("sub")
    elif claim in ("preferred_username", "username"):
        value = payload.get("preferred_username")
    else:
        value = payload.get(claim)
    if not value:
        value = payload.get("sub") or payload.get("preferred_username") or payload.get("email")
    return str(value) if value else "anonymous"


def _resolve_username(payload: dict) -> str:
    value = payload.get("preferred_username") or payload.get("email") or payload.get("sub")
    return str(value) if value else "anonymous"


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
    return RequestUser(user_id=user_id, username=username, sub=sub)


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
    return RequestUser(user_id=user_id, username=username, sub=sub)
