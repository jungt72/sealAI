# 📁 backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

* prüft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen für Endpoints (HTTP & WS)
* WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, WebSocket, status, Header

from app.core.config import settings              # <-- korrekter Pfad!
from app.services.auth.token import verify_access_token


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = Header(default=None),
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
    payload = verify_access_token(token)
    return payload.get("preferred_username", "anonymous")


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency – für Chat-Streaming
#    (unterstützt Header *oder* Query-Parameter ?token=/ ?access_token=)
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> str:
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

    payload = verify_access_token(token)
    return payload.get("preferred_username", "anonymous")
