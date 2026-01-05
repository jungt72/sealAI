import { deleteTokens, getTokens, updateTokens } from "@/lib/auth-token-store";

const CLOCK_SKEW_SECONDS = 60;
const REFRESH_TIMEOUT_MS = 10_000;
const SESSION_MAX_AGE_SECONDS = Number(process.env.NEXTAUTH_SESSION_MAXAGE ?? "1800");

export type KeycloakToken = {
  accessToken?: string | null;
  refreshToken?: string | null;
  idToken?: string | null;
  expires_at?: number | null;
  accessTokenExpires?: number | null;
  refreshTokenExpires?: number | null;
  jti?: string | null;
  error?: string | null;
};

const normalizeIssuer = (issuer?: string): string => {
  return (issuer ?? "").replace(/\/+$/, "");
};

export const isTokenExpired = (expiresAt?: number | null): boolean => {
  if (typeof expiresAt !== "number") return true;
  const now = Math.floor(Date.now() / 1000);
  return now >= expiresAt - CLOCK_SKEW_SECONDS;
};

export const isRefreshTokenExpired = (refreshExpiresAt?: number | null): boolean => {
  if (typeof refreshExpiresAt !== "number") return true;
  const now = Math.floor(Date.now() / 1000);
  return now >= refreshExpiresAt - CLOCK_SKEW_SECONDS;
};

const buildTokenEndpoint = (issuer: string) => `${issuer}/protocol/openid-connect/token`;

export const refreshAccessToken = async (token: KeycloakToken): Promise<KeycloakToken> => {
  const issuer = normalizeIssuer(process.env.KEYCLOAK_ISSUER);
  const clientId = process.env.KEYCLOAK_CLIENT_ID;
  const jti = token.jti ?? null;

  if (!issuer || !clientId || !jti) {
    console.warn("Keycloak refresh skipped: missing issuer/client or token id.");
    return {
      ...token,
      accessToken: null,
      expires_at: null,
      error: "RefreshAccessTokenError",
    };
  }

  const stored = await getTokens(jti);
  const refreshToken = stored?.refreshToken ?? null;
  if (!refreshToken) {
    console.warn("Keycloak refresh skipped: refresh token missing in store.");
    return {
      ...token,
      accessToken: null,
      expires_at: null,
      error: "RefreshAccessTokenError",
    };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);

  try {
    const params = new URLSearchParams({
      grant_type: "refresh_token",
      client_id: clientId,
      refresh_token: refreshToken,
    });

    const clientSecret = process.env.KEYCLOAK_CLIENT_SECRET;
    if (clientSecret) {
      params.append("client_secret", clientSecret);
    }

    const res = await fetch(buildTokenEndpoint(issuer), {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params.toString(),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`Keycloak token refresh failed (${res.status})`);
    }

    const data = await res.json();
    const now = Math.floor(Date.now() / 1000);
    const expiresIn = Number(data.expires_in);
    const expiresAt =
      Number.isFinite(expiresIn) && expiresIn > 0 ? now + expiresIn : token.expires_at ?? null;
    const refreshExpiresIn = Number(data.refresh_expires_in ?? data.refresh_token_expires_in);
    const refreshExpiresAt =
      Number.isFinite(refreshExpiresIn) && refreshExpiresIn > 0
        ? now + refreshExpiresIn
        : stored?.refreshTokenExpires ?? now + SESSION_MAX_AGE_SECONDS;

    await updateTokens(
      jti,
      {
        accessToken: data.access_token ?? stored?.accessToken ?? null,
        refreshToken: data.refresh_token ?? refreshToken,
        idToken: data.id_token ?? stored?.idToken ?? null,
        expires_at: expiresAt,
        refreshTokenExpires: refreshExpiresAt,
      },
      SESSION_MAX_AGE_SECONDS,
    );

    return {
      ...token,
      accessToken: data.access_token ?? stored?.accessToken ?? token.accessToken ?? null,
      refreshToken: data.refresh_token ?? refreshToken,
      idToken: data.id_token ?? stored?.idToken ?? null,
      expires_at: expiresAt,
      refreshTokenExpires: refreshExpiresAt,
      error: null,
    };
  } catch (error) {
    console.error("Keycloak token refresh failed", {
      reason: error instanceof Error ? error.message : String(error),
    });
    await deleteTokens(jti);
    return {
      ...token,
      accessToken: null,
      expires_at: null,
      error: "RefreshAccessTokenError",
    };
  } finally {
    clearTimeout(timeout);
  }
};
