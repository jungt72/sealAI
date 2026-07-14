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

const AUTH_TRANSACTION_KEY = "sealai.v2.oidc.transaction.v1";
const AUTH_TRANSACTION_TTL_MS = 5 * 60_000;

interface AuthTransaction {
  version: 1;
  verifier: string;
  state: string;
  nonce: string;
  createdAt: number;
  issuer: string;
  clientId: string;
  redirectUri: string;
}

// --- in-memory token store: a module-local holder, NEVER persisted to web storage ----------------
let _accessToken: string | null = null;
let _expiresAt = 0; // epoch ms
let _refreshToken: string | null = null; // in-memory ONLY; rotated on every refresh, dropped on clear
let _refreshInFlight: Promise<TokenResponse> | null = null; // single-flight guard (rotation-safe)
let _tokenGeneration = 0; // invalidates a refresh response that races logout/session clearing

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
export function clearAccessToken(): void {
  _tokenGeneration += 1;
  _accessToken = null;
  _expiresAt = 0;
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

function canonicalIssuer(value: string): string {
  return value.replace(/\/+$/, "");
}

function assertOidcConfig(cfg: OidcConfig): void {
  const issuer = new URL(cfg.issuer);
  const redirect = new URL(cfg.redirectUri);
  const postLogout = cfg.postLogoutRedirectUri ? new URL(cfg.postLogoutRedirectUri) : null;
  const localHttp = issuer.protocol === "http:" && issuer.hostname === "localhost";
  if ((issuer.protocol !== "https:" && !localHttp) || issuer.search || issuer.hash) {
    throw new Error("OIDC configuration rejected");
  }
  if (redirect.origin !== location.origin || redirect.search || redirect.hash || !cfg.clientId) {
    throw new Error("OIDC configuration rejected");
  }
  if (
    postLogout &&
    (postLogout.origin !== location.origin || postLogout.search || postLogout.hash)
  ) {
    throw new Error("OIDC configuration rejected");
  }
}

function fixedTimeEqual(left: string, right: string): boolean {
  let mismatch = left.length ^ right.length;
  const width = Math.max(left.length, right.length);
  for (let index = 0; index < width; index += 1) {
    mismatch |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return mismatch === 0;
}

/** Create one short-lived authorization transaction for this tab. Tokens remain memory-only; the
 * PKCE verifier/state/nonce are consumed before callback exchange and cannot be replayed. */
export async function beginAuthorization(
  cfg: OidcConfig,
  opts: { silent?: boolean; now?: number } = {},
): Promise<string> {
  assertOidcConfig(cfg);
  const tx: AuthTransaction = {
    version: 1,
    verifier: randomVerifier(),
    state: randomVerifier(),
    nonce: randomVerifier(),
    createdAt: opts.now ?? Date.now(),
    issuer: canonicalIssuer(cfg.issuer),
    clientId: cfg.clientId,
    redirectUri: cfg.redirectUri,
  };
  sessionStorage.setItem(AUTH_TRANSACTION_KEY, JSON.stringify(tx));
  return authorizeUrl(cfg, { ...tx, silent: opts.silent });
}

export function authorizeUrl(
  cfg: OidcConfig,
  opts: { verifier: string; state: string; nonce: string; silent?: boolean },
): Promise<string> {
  assertOidcConfig(cfg);
  return challengeFromVerifier(opts.verifier).then((challenge) => {
    const p = new URLSearchParams({
      client_id: cfg.clientId,
      response_type: "code",
      redirect_uri: cfg.redirectUri,
      scope: cfg.scope ?? "openid email profile",
      state: opts.state,
      nonce: opts.nonce,
      code_challenge: challenge,
      code_challenge_method: "S256",
    });
    if (opts.silent) p.set("prompt", "none"); // silent renewal via the SSO session
    return `${canonicalIssuer(cfg.issuer)}/protocol/openid-connect/auth?${p.toString()}`;
  });
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
  id_token?: string;
}

function decodeJwtClaims(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) throw new Error("OIDC response rejected");
  try {
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as unknown;
    if (!claims || typeof claims !== "object" || Array.isArray(claims)) {
      throw new Error("invalid claims");
    }
    return claims as Record<string, unknown>;
  } catch {
    throw new Error("OIDC response rejected");
  }
}

function validateIdToken(
  token: string | undefined,
  cfg: OidcConfig,
  expectedNonce: string,
  nowMs = Date.now(),
): void {
  if (!token) throw new Error("OIDC response rejected");
  const claims = decodeJwtClaims(token);
  const audience = claims.aud;
  const audienceMatches =
    audience === cfg.clientId ||
    (Array.isArray(audience) && audience.some((entry) => entry === cfg.clientId));
  const multiAudience = Array.isArray(audience) && audience.length > 1;
  const nowSeconds = Math.floor(nowMs / 1000);
  if (
    claims.iss !== canonicalIssuer(cfg.issuer) ||
    !audienceMatches ||
    (multiAudience && claims.azp !== cfg.clientId) ||
    typeof claims.nonce !== "string" ||
    !fixedTimeEqual(claims.nonce, expectedNonce) ||
    typeof claims.exp !== "number" ||
    claims.exp <= nowSeconds - 30 ||
    typeof claims.iat !== "number" ||
    claims.iat > nowSeconds + 60 ||
    claims.iat < nowSeconds - 300
  ) {
    throw new Error("OIDC response rejected");
  }
}

function consumeAuthorizationTransaction(
  cfg: OidcConfig,
  callbackUrl: URL,
  nowMs = Date.now(),
): { code: string; verifier: string; nonce: string } {
  assertOidcConfig(cfg);
  const serialized = sessionStorage.getItem(AUTH_TRANSACTION_KEY);
  // One-time semantics: remove before parsing/comparison/network I/O.
  sessionStorage.removeItem(AUTH_TRANSACTION_KEY);
  if (!serialized) throw new Error("OIDC callback rejected");

  let raw: unknown;
  try {
    raw = JSON.parse(serialized);
  } catch {
    throw new Error("OIDC callback rejected");
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("OIDC callback rejected");
  }
  const tx = raw as Partial<AuthTransaction>;
  const state = callbackUrl.searchParams.get("state");
  const code = callbackUrl.searchParams.get("code");
  const responseIssuer = callbackUrl.searchParams.get("iss");
  const redirect = new URL(cfg.redirectUri);
  if (
    tx.version !== 1 ||
    typeof tx.createdAt !== "number" ||
    tx.createdAt > nowMs + 30_000 ||
    nowMs - tx.createdAt > AUTH_TRANSACTION_TTL_MS ||
    typeof tx.state !== "string" ||
    typeof state !== "string" ||
    callbackUrl.searchParams.getAll("state").length !== 1 ||
    !fixedTimeEqual(tx.state, state) ||
    typeof tx.verifier !== "string" ||
    !/^[A-Za-z0-9_-]{43,128}$/.test(tx.verifier) ||
    typeof tx.nonce !== "string" ||
    !/^[A-Za-z0-9_-]{43,128}$/.test(tx.nonce) ||
    tx.issuer !== canonicalIssuer(cfg.issuer) ||
    tx.clientId !== cfg.clientId ||
    tx.redirectUri !== cfg.redirectUri ||
    callbackUrl.origin !== redirect.origin ||
    callbackUrl.pathname !== redirect.pathname ||
    (responseIssuer !== null && responseIssuer !== canonicalIssuer(cfg.issuer)) ||
    callbackUrl.searchParams.has("error") ||
    typeof code !== "string" ||
    callbackUrl.searchParams.getAll("code").length !== 1 ||
    !code ||
    code.length > 2048
  ) {
    throw new Error("OIDC callback rejected");
  }
  return { code, verifier: tx.verifier, nonce: tx.nonce };
}

/** Remove protocol credentials from browser history before validation/exchange can yield or fail. */
export function scrubAuthorizationCallback(): void {
  window.history.replaceState({}, "", "/dashboard/");
}

export async function completeAuthorizationCallback(
  cfg: OidcConfig,
  callbackUrl: URL,
  nowMs = Date.now(),
): Promise<TokenResponse> {
  const tx = consumeAuthorizationTransaction(cfg, callbackUrl, nowMs);
  return exchangeCode(cfg, tx.code, tx.verifier, { expectedNonce: tx.nonce, nowMs });
}

export function discardAuthorizationTransaction(): void {
  sessionStorage.removeItem(AUTH_TRANSACTION_KEY);
}

export async function exchangeCode(
  cfg: OidcConfig,
  code: string,
  verifier: string,
  validation: { expectedNonce?: string; nowMs?: number } = {},
): Promise<TokenResponse> {
  assertOidcConfig(cfg);
  const res = await fetch(`${canonicalIssuer(cfg.issuer)}/protocol/openid-connect/token`, {
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
  if (
    !tok ||
    typeof tok.access_token !== "string" ||
    !tok.access_token ||
    typeof tok.expires_in !== "number" ||
    !Number.isFinite(tok.expires_in) ||
    tok.expires_in <= 0 ||
    tok.expires_in > 86_400 ||
    (tok.refresh_token !== undefined && typeof tok.refresh_token !== "string") ||
    (tok.id_token !== undefined && typeof tok.id_token !== "string")
  ) {
    throw new Error("OIDC response rejected");
  }
  if (validation.expectedNonce) {
    validateIdToken(tok.id_token, cfg, validation.expectedNonce, validation.nowMs);
  }
  // A completed authorization-code exchange starts a new local token generation. Any older
  // refresh response still in flight belongs to the superseded session and may no longer mutate
  // this token set, regardless of whether that old response succeeds or fails.
  _tokenGeneration += 1;
  setAccessToken(tok.access_token, tok.expires_in); // in memory only
  // Replace the whole credential set. If this response has no refresh token, retaining one from
  // an older authorization session would cross session boundaries.
  _refreshToken = tok.refresh_token || null; // in memory only → silent refresh
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
  assertOidcConfig(cfg);
  if (!_refreshToken) throw new Error("no refresh token");
  const tokenGeneration = _tokenGeneration;
  const presentedRefreshToken = _refreshToken;
  const res = await fetch(`${canonicalIssuer(cfg.issuer)}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: cfg.clientId,
      refresh_token: presentedRefreshToken,
    }),
  });
  if (!res.ok) {
    // Clear only the exact token generation that produced this request. A delayed failure from a
    // logged-out/superseded session must never erase a freshly established session's token.
    if (
      tokenGeneration === _tokenGeneration &&
      _refreshToken === presentedRefreshToken
    ) {
      _refreshToken = null; // rotated-away / expired / revoked → never retry with it
    }
    throw new Error(`refresh failed: ${res.status}`);
  }
  const tok = (await res.json()) as TokenResponse;
  if (
    !tok ||
    typeof tok.access_token !== "string" ||
    !tok.access_token ||
    typeof tok.expires_in !== "number" ||
    !Number.isFinite(tok.expires_in) ||
    tok.expires_in <= 0 ||
    tok.expires_in > 86_400 ||
    (tok.refresh_token !== undefined && typeof tok.refresh_token !== "string") ||
    (tok.id_token !== undefined && typeof tok.id_token !== "string")
  ) {
    if (
      tokenGeneration === _tokenGeneration &&
      _refreshToken === presentedRefreshToken
    ) {
      _refreshToken = null;
    }
    throw new Error("OIDC response rejected");
  }
  // Logout/401 clearing wins over a response already in flight. Without this generation check,
  // a delayed refresh could republish access and refresh tokens after the local session ended.
  if (tokenGeneration !== _tokenGeneration) throw new Error("refresh superseded");
  setAccessToken(tok.access_token, tok.expires_in);
  // With rotation enabled, the presented token is consumed. If the IdP omits a replacement,
  // retain no dead credential and let the caller fall back to prompt=none re-authentication.
  _refreshToken = tok.refresh_token || null;
  return tok;
}

// --- RP-initiated logout (OIDC end-session) --------------------------------------------------------
/** End-session URL on the realm. We deliberately omit ``id_token_hint``: Keycloak may show its
 * confirmation screen, but no authentication identifier enters history, request lines or proxy
 * logs. The post-logout URI remains an exact allowlisted public callback. */
export function logoutUrl(cfg: OidcConfig): string {
  assertOidcConfig(cfg);
  const p = new URLSearchParams({
    client_id: cfg.clientId,
    post_logout_redirect_uri: cfg.postLogoutRedirectUri ?? `${location.origin}/dashboard/`,
  });
  return `${canonicalIssuer(cfg.issuer)}/protocol/openid-connect/logout?${p.toString()}`;
}

/** The Abmelden action: build the end-session URL without an authentication token, clear ALL local tokens
 * FIRST (the SPA is logged out even if the redirect is interrupted), then leave for Keycloak.
 * `navigate` is injectable for tests; production uses a full-page redirect (front-channel). */
export function rpInitiatedLogout(
  cfg: OidcConfig,
  navigate: (url: string) => void = (url) => {
    window.location.href = url;
  },
): void {
  const url = logoutUrl(cfg);
  clearAccessToken();
  navigate(url);
}
