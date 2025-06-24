# 📁 backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

* prüft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen für Endpoints (HTTP & WS)
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, WebSocket, status

from app.core.config import settings              # <-- korrekter Pfad!
from app.services.auth.token import verify_access_token


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = None,
) -> str:
    """
    Liefert den `preferred_username` aus dem gültigen JWT,
    sonst → 401 UNAUTHORIZED.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )

    token = authorization.removeprefix("Bearer ").strip()
    payload = await verify_access_token(token)
    return payload.get("preferred_username", "anonymous")


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency – für Chat-Streaming
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> str:
    """
    Prüft das `Authorization:`-Header beim WS-Handshake
    und gibt den Usernamen zurück.
    Bei Fehler → WS-Close (1008) + HTTPException.
    """
    auth_header = websocket.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        await websocket.close(code=1008)  # Policy violation
        raise HTTPException(              # wird von FastAPI intern geloggt
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )

    token = auth_header.removeprefix("Bearer ").strip()
    payload = await verify_access_token(token)
    return payload.get("preferred_username", "anonymous")
