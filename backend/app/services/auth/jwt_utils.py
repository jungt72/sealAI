# 📁 backend/app/services/auth/jwt_utils.py
from fastapi import HTTPException, status

def extract_username_from_payload(payload: dict) -> str:
    """
    Extrahiert den Nutzernamen aus dem bereits verifizierten JWT-Payload.
    """
    try:
        return (
            payload.get("preferred_username")
            or payload.get("email")
            or payload["sub"]
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username claim missing in token"
        )
