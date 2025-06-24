from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

router = APIRouter()

@router.get("/login", tags=["Auth"])
def login_redirect():
    """
    Leitet den Benutzer zum Keycloak-Login weiter.
    Die Parameter müssen mit der Konfiguration deines Keycloak-Clients übereinstimmen.
    """
    keycloak_base_url = "https://auth.sealai.net/realms/sealAI/protocol/openid-connect/auth"
    # Ersetze diese Werte mit deinen konfigurierten Angaben:
    client_id = "nextauth"  # oder "sealai-backend", je nachdem, was du in Keycloak als Client definiert hast
    redirect_uri = "https://sealai.net/api/auth/callback/keycloak"  # muss zu deinen Keycloak-Redirect-URIs passen
    response_type = "code"
    scope = "openid"

    params = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "scope": scope
    }

    # Erzeuge die vollständige URL
    url = f"{keycloak_base_url}?{urlencode(params)}"
    return RedirectResponse(url)
