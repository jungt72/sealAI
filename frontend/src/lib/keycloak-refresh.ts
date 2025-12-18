const CLOCK_SKEW_SECONDS = 60;
const REFRESH_TIMEOUT_MS = 10_000;

export type KeycloakToken = {
  accessToken?: string | null;
  refreshToken?: string | null;
  idToken?: string | null;
  expires_at?: number | null;
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

const buildTokenEndpoint = (issuer: string) => `${issuer}/protocol/openid-connect/token`;

export const refreshAccessToken = async (token: KeycloakToken): Promise<KeycloakToken> => {
  const issuer = normalizeIssuer(process.env.KEYCLOAK_ISSUER);
  const clientId = process.env.KEYCLOAK_CLIENT_ID;

  if (!issuer || !clientId || !token.refreshToken) {
    return token;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);

  try {
    const params = new URLSearchParams({
      grant_type: "refresh_token",
      client_id: clientId,
      refresh_token: token.refreshToken,
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

    return {
      ...token,
      accessToken: data.access_token ?? token.accessToken,
      refreshToken: data.refresh_token ?? token.refreshToken,
      idToken: data.id_token ?? token.idToken,
      expires_at: expiresAt,
      error: null,
    };
  } catch (error) {
    console.error("Keycloak token refresh failed", {
      reason: error instanceof Error ? error.message : String(error),
    });
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
