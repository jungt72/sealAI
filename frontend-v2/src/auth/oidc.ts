/* M7 auth (build-gate check 4) — OIDC Authorization-Code + PKCE against a Keycloak PUBLIC client
 * (sealai-v2). NO client secret in the browser; NOT the implicit flow. The access token is held
 * IN MEMORY ONLY (never localStorage/sessionStorage) so an XSS cannot read it from storage; on
 * reload, silent re-auth (prompt=none) against the Keycloak SSO session is preferred over a stored
 * refresh token. The token carries aud (matching the backend-v2 validator) + tenant_id + sid + sub;
 * the client never asserts identity — it only sends the Bearer (M6c no-header-trust). */

export interface OidcConfig {
  issuer: string; // https://sealingai.com/realms/sealAI
  clientId: string; // sealai-v2 (public)
  redirectUri: string; // https://sealingai.com/dashboard/callback
  scope?: string; // "openid email profile"
}

// --- in-memory token store: a module-local holder, NEVER persisted to web storage ----------------
let _accessToken: string | null = null;
let _expiresAt = 0; // epoch ms

export function setAccessToken(token: string, expiresInSec: number): void {
  _accessToken = token;
  _expiresAt = Date.now() + expiresInSec * 1000;
}
export function getAccessToken(): string | null {
  if (!_accessToken || Date.now() >= _expiresAt - 30_000) return null; // 30s skew → treat as stale
  return _accessToken;
}
export function clearAccessToken(): void {
  _accessToken = null;
  _expiresAt = 0;
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
  return tok;
}
