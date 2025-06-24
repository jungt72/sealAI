# backend/app/api/v1/dependencies/auth.py
"""
Auth-Dependency: Extrahiert den Benutzer-Namen („preferred_username“)
aus dem Bearer-Token im Request-Header.  FastAPI kann diese Funktion
mittels `Depends` injizieren.
"""

from fastapi import Request, HTTPException, status

from app.services.auth.token import verify_access_token


async def get_current_request_user(request: Request) -> str:
    """
    Liefert den Username aus dem JWT oder wirft 401,
    wenn der Header fehlt / ungültig ist.
    """
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )

    token = auth_header.removeprefix("Bearer ").strip()
    payload = await verify_access_token(token)
    return payload.get("preferred_username", "anonymous")


# Damit `from app.api.v1.dependencies.auth import get_current_request_user`
# funktioniert, exportieren wir die Funktion explizit.
__all__ = ["get_current_request_user"]
