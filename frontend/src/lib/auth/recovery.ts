const KEYCLOAK_CALLBACK_PATH = "/api/auth/callback/keycloak";

/**
 * Recover a known stale Keycloak browser transaction before Auth.js validates its now-expired
 * state cookie. Keycloak returns this exact pair when an old login form is submitted after its
 * authentication session has expired. Passing it into Auth.js turns a recoverable login timeout
 * into `InvalidCheck` and the misleading `Configuration` 500 page.
 *
 * The dashboard starts a fresh, first-party OIDC/PKCE flow and therefore is the safest recovery
 * target. Every other provider/callback error remains with Auth.js and its custom error page so a
 * real configuration defect is never silently hidden.
 */
export function expiredKeycloakRecoveryUrl(requestUrl: URL): URL | null {
  if (requestUrl.pathname !== KEYCLOAK_CALLBACK_PATH) return null;
  if (requestUrl.searchParams.get("error") !== "temporarily_unavailable") return null;
  if (requestUrl.searchParams.get("error_description") !== "authentication_expired") return null;

  return new URL("/dashboard/", requestUrl.origin);
}
