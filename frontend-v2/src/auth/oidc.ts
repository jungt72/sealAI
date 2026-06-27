/* M7 auth (build-gate check 4) — OIDC Authorization-Code + PKCE (S256) against a Keycloak PUBLIC
 * client (sealai-v2). NO client secret in the browser; NOT the implicit flow.
 *
 * Token lifecycle (the "big-platform" pattern — short access token + seamless silent refresh):
 *  - The access token + the refresh token are held IN MEMORY ONLY (never localStorage/sessionStorage)
 *    so an XSS cannot read them from storage and they vanish on tab close.
 *  - DURING a session the SPA proactively refreshes ~well before expiry via the refresh_token grant
 *    (``refreshTokens``). The realm ROTATES refresh tokens (revokeRefreshToken + maxReuse=0): each
 *    refresh returns a NEW one-time refresh token, so a leaked refresh token is single-use + detected.
 *  - On RELOAD (memory is gone) the SPA silently re-auths via prompt=none against the Keycloak SSO
 *    session cookie (httpOnly, first-party) — no token survives the reload.
 *  - On a definitive refresh failure (session ended / token revoked) the SPA falls back to re-login.
 *
 * The token carries aud (matching the backend-v2 validator) + tenant_id + sid + sub + roles; the
 * client never asserts identity — it only sends the Bearer (M6c no-header-trust). */

export interface OidcConfig {
  issuer: string; // https://sealingai.com/realms/sealAI
  clientId: string; // sealai-v2 (public)
  redirectUri: string; // https://sealingai.com/dashboard/callback
  scope?: string; // "openid email profile"
  postLogoutRedirectUri?: string; // https://sealingai.com/dashboard/ (must be allowlisted in Keycloak)
}

// --- in-memory token store: a module-local holder, NEVER persisted to web storage ----------------
let _accessToken: string | null = null;
let _expiresAt = 0; // epoch ms
let _idToken: string | null = null; // kept ONLY as the RP-initiated-logout id_token_hint
let _refreshToken: string | null = null; // in-memory ONLY; rotated on every refresh, dropped on clear
let _refreshInFlight: Promise<TokenResponse> | null = null; // single-flight guard (rotation-safe)

export function setAccessToken(token: string, expiresInSec: number): void {
  _accessToken = token;
  _expiresAt = Date.now() + expiresInSec * 1000;
}
export function getAccessToken(): string | null {
  if (!_accessToken || Date.now() >= _expiresAt - 30_000) return null; // 30s skew → treat as stale
  return _accessToken;
}
/** Milliseconds until the access token expires (<=0 if none / already expired) — drives the proactive
 * silent-refresh scheduler. NOT the 30s-skew view of getAccessToken; the true expiry. */
export function msUntilExpiry(): number {
  return _accessToken ? _expiresAt - Date.now() : 0;
}
export function hasRefreshToken(): boolean {
  return _refreshToken !== null;
}
export function setIdToken(token: string | null): void {
  _idToken = token;
}
// no expiry check: an expired id_token is still a valid logout hint (it only names the session)
export function getIdToken(): string | null {
  return _idToken;
}
export function clearAccessToken(): void {
  _accessToken = null;
  _expiresAt = 0;
  _idToken = null;
  _refreshToken = null;
}

// --- display-only identity claim -------------------------------------------------------------------
/** Greeting name from the access token's `given_name` claim (OIDC `profile` scope, Part 2).
 * Decode-only — NO signature check (the backend verifies every API call; this is cosmetic UI text)
 * and NO logging (neither the token nor the name may reach the console — PII). Any missing,
 * malformed, or non-string input → null, so the caller falls back to the nameless greeting. */
export function givenNameFromToken(token: string | null): string | null {
  if (!token) return null;
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    const name = claims.given_name;
    return typeof name === "string" && name.trim() ? name.trim() : null;
  } catch {
    return null; // malformed token → nameless greeting, never an error or a log line
  }
}

/** Realm roles from the verified token (Keycloak realm_access.roles) — display-gating ONLY (show the
 * admin UI). The BACKEND independently re-checks the role on every /admin call, so a tampered token
 * never grants access; this only decides what the SPA bothers to render. */
export function rolesFromToken(token: string | null): string[] {
  if (!token) return [];
  const payload = token.split(".")[1];
  if (!payload) return [];
  try {
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    const realm = claims.realm_access as { roles?: unknown } | undefined;
    const roles = realm?.roles;
    return Array.isArray(roles)
      ? roles.filter((r): r is string => typeof r === "string")
      : [];
  } catch {
    return [];
  }
}

/** The manufacturer-partner id from the verified token (Keycloak hersteller_id claim) — scopes the
 * manufacturer self-service view to their OWN record. Display-gating only; the backend independently
 * re-derives + enforces it on every /partner/me call. */
export function herstellerIdFromToken(token: string | null): string {
  if (!token) return "";
  const payload = token.split(".")[1];
  if (!payload) return "";
  try {
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    const id = claims.hersteller_id;
    return typeof id === "string" ? id : "";
  } catch {
    return "";
  }
}

// --- PKCE ----------------------------------------------------------------------------------------
function b64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function randomVerifier(): string {
  return b64url(crypto.getRandomValues(new Uint8Array(32)));
}
export async function challengeFromVerifier(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return b64url(digest); // S256
}

export function authorizeUrl(
  cfg: OidcConfig,
  opts: { verifier: string; state: string; silent?: boolean },
): Promise<string> {
  return challengeFromVerifier(opts.verifier).then((challenge) => {
    const p = new URLSearchParams({
      client_id: cfg.clientId,
      response_type: "code",
      redirect_uri: cfg.redirectUri,
      scope: cfg.scope ?? "openid email profile",
      state: opts.state,
      code_challenge: challenge,
      code_challenge_method: "S256",
    });
    if (opts.silent) p.set("prompt", "none"); // silent renewal via the SSO session
    return `${cfg.issuer}/protocol/openid-connect/auth?${p.toString()}`;
  });
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
  id_token?: string;
}

export async function exchangeCode(
  cfg: OidcConfig,
  code: string,
  verifier: string,
): Promise<TokenResponse> {
  const res = await fetch(`${cfg.issuer}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: cfg.clientId,
      code,
      redirect_uri: cfg.redirectUri,
      code_verifier: verifier,
    }),
  });
  if (!res.ok) throw new Error(`token exchange failed: ${res.status}`);
  const tok = (await res.json()) as TokenResponse;
  setAccessToken(tok.access_token, tok.expires_in); // in memory only
  if (tok.refresh_token) _refreshToken = tok.refresh_token; // in memory only → silent refresh
  setIdToken(tok.id_token ?? null); // held only as the future logout id_token_hint
  return tok;
}

/** Proactive silent refresh via the refresh_token grant. SINGLE-FLIGHT: concurrent callers (the
 * scheduler timer + the visibility/focus handler) coalesce onto ONE in-flight request. This is
 * non-negotiable under refresh-token ROTATION (maxReuse=0) — two parallel refreshes would each present
 * the same one-time token; Keycloak treats the second as replay and REVOKES the whole session. So all
 * callers await the one request. On a non-OK response the (now-useless) refresh token is dropped + the
 * call throws, so the caller falls back to prompt=none re-auth / re-login. */
export function refreshTokens(cfg: OidcConfig): Promise<TokenResponse> {
  if (_refreshInFlight) return _refreshInFlight;
  _refreshInFlight = _doRefresh(cfg).finally(() => {
    _refreshInFlight = null;
  });
  return _refreshInFlight;
}

async function _doRefresh(cfg: OidcConfig): Promise<TokenResponse> {
  if (!_refreshToken) throw new Error("no refresh token");
  const res = await fetch(`${cfg.issuer}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: cfg.clientId,
      refresh_token: _refreshToken,
    }),
  });
  if (!res.ok) {
    _refreshToken = null; // rotated-away / expired / revoked → useless, never retry with it
    throw new Error(`refresh failed: ${res.status}`);
  }
  const tok = (await res.json()) as TokenResponse;
  setAccessToken(tok.access_token, tok.expires_in);
  if (tok.refresh_token) _refreshToken = tok.refresh_token; // ROTATION: keep the new one-time token
  if (tok.id_token) setIdToken(tok.id_token);
  return tok;
}

// --- RP-initiated logout (OIDC end-session) --------------------------------------------------------
/** End-session URL on the realm. id_token_hint lets Keycloak log out WITHOUT a confirmation screen;
 * absent (e.g. after a reload — tokens are memory-only), client_id still identifies the client and
 * Keycloak shows its confirm prompt — logout still works, one extra click. The
 * post_logout_redirect_uri must be allowlisted on the Keycloak client (owner config). */
export function logoutUrl(cfg: OidcConfig, opts: { idToken?: string | null } = {}): string {
  const p = new URLSearchParams({
    client_id: cfg.clientId,
    post_logout_redirect_uri: cfg.postLogoutRedirectUri ?? `${location.origin}/dashboard/`,
  });
  if (opts.idToken) p.set("id_token_hint", opts.idToken);
  return `${cfg.issuer}/protocol/openid-connect/logout?${p.toString()}`;
}

/** The Abmelden action: build the end-session URL from the held id_token, clear ALL local tokens
 * FIRST (the SPA is logged out even if the redirect is interrupted), then leave for Keycloak.
 * `navigate` is injectable for tests; production uses a full-page redirect (front-channel). */
export function rpInitiatedLogout(
  cfg: OidcConfig,
  navigate: (url: string) => void = (url) => {
    window.location.href = url;
  },
): void {
  const url = logoutUrl(cfg, { idToken: getIdToken() });
  clearAccessToken(); // clears access + id token; the hint is already baked into the URL
  navigate(url);
}
