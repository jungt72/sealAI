from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

from app.core.config import settings

router = APIRouter()

@router.get("/login", tags=["Auth"])
def login_redirect(
    state: str | None = Query(default=None, description="Optional OIDC state passthrough"),
    nonce: str | None = Query(default=None, description="Optional OIDC nonce passthrough"),
):
    """
    Leitet den Benutzer zum Keycloak-Login weiter.
    Die Parameter müssen mit der Konfiguration deines Keycloak-Clients übereinstimmen.
    """
    # Aus ENV/Settings ableiten, statt Hardcoding
    keycloak_base_url = f"{settings.keycloak_issuer.rstrip('/')}/protocol/openid-connect/auth"

    client_id = settings.keycloak_client_id
    # NextAuth baut die Callback-Route immer unter /api/auth/callback/<provider>
    redirect_uri = f"{settings.nextauth_url.rstrip('/')}/api/auth/callback/keycloak"

    response_type = "code"
    # Scope analog zum NextAuth-Provider
    scope = "openid profile email"

    params = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "scope": scope
    }

    # Optional: state/nonce durchreichen, wenn gesetzt
    if state:
        params["state"] = state
    if nonce:
        params["nonce"] = nonce

    # Erzeuge die vollständige URL
    url = f"{keycloak_base_url}?{urlencode(params)}"
    return RedirectResponse(url)
