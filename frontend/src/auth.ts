import NextAuth from "next-auth";
import type { JWT } from "next-auth/jwt";
import KeycloakProvider from "next-auth/providers/keycloak";

const KEYCLOAK_ISSUER =
  process.env.KEYCLOAK_ISSUER ?? "https://auth.sealai.net/realms/sealAI";
const KEYCLOAK_AUTHORIZATION_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/auth`;
const KEYCLOAK_TOKEN_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/token`;
const KEYCLOAK_USERINFO_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/userinfo`;

// ---------------------------------------------------------------------------
// Type augmentation — avoids `as any` casts in callbacks
// ---------------------------------------------------------------------------
declare module "next-auth" {
  interface Session {
    accessToken?: string;
    idToken?: string;
    /** Set when the background refresh failed; UI should prompt re-login */
    error?: "RefreshTokenError";
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    idToken?: string;
    refreshToken?: string;
    /** Unix timestamp (seconds) when the access token expires */
    expiresAt?: number;
    error?: "RefreshTokenError";
  }
}

// ---------------------------------------------------------------------------
// Token refresh — called when the access token has expired
// Uses the public issuer so the host-based PM2 frontend stays aligned with the browser flow
// ---------------------------------------------------------------------------
async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const response = await fetch(KEYCLOAK_TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: process.env.KEYCLOAK_CLIENT_ID!,
        client_secret: process.env.KEYCLOAK_CLIENT_SECRET!,
        refresh_token: token.refreshToken!,
      }),
    });

    const refreshed = await response.json();
    if (!response.ok) throw refreshed;

    return {
      ...token,
      accessToken: refreshed.access_token,
      // Keycloak rotates the id_token only when a new id_token is issued
      idToken: refreshed.id_token ?? token.idToken,
      // Keycloak may issue a new refresh token (rotation); fall back to the old one if not
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + (refreshed.expires_in as number),
      error: undefined,
    };
  } catch {
    // Refresh failed (revoked token, Keycloak down, etc.)
    // Returning error here causes the session callback to surface it to the UI
    return { ...token, error: "RefreshTokenError" };
  }
}

// ---------------------------------------------------------------------------
// NextAuth configuration
// ---------------------------------------------------------------------------
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    KeycloakProvider({
      clientId: process.env.KEYCLOAK_CLIENT_ID as string,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET as string,

      // Issuer must match the external URL so JWT `iss` validation passes
      issuer: KEYCLOAK_ISSUER,

      wellKnown: undefined, // disable auto-discovery — endpoints are pinned below

      authorization: {
        params: {
          // offline_access is required to receive a refresh_token from Keycloak
          scope: "openid email profile offline_access",
        },
        url: KEYCLOAK_AUTHORIZATION_URL,
      },
      token: KEYCLOAK_TOKEN_URL,
      userinfo: KEYCLOAK_USERINFO_URL,

      checks: ["pkce", "state"],
      allowDangerousEmailAccountLinking: true,
    }),
  ],

  trustHost: true,

  callbacks: {
    // ------------------------------------------------------------------
    // jwt — runs on every request that involves a token
    // ------------------------------------------------------------------
    async jwt({ token, account }) {
      // Initial sign-in: Keycloak hands us the full token set
      if (account) {
        return {
          ...token,
          accessToken:  account.access_token,
          idToken:      account.id_token,
          refreshToken: account.refresh_token,
          // account.expires_at is an absolute Unix timestamp (seconds)
          expiresAt:    account.expires_at,
        };
      }

      // Token still valid (with 30 s buffer to account for clock skew)
      if (Date.now() < (token.expiresAt ?? 0) * 1000 - 30_000) {
        return token;
      }

      // Access token expired — attempt silent refresh
      return refreshAccessToken(token);
    },

    // ------------------------------------------------------------------
    // session — shapes the client-facing session object
    // ------------------------------------------------------------------
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.idToken     = token.idToken;
      // Surface refresh errors so the UI can redirect to /api/auth/signin
      if (token.error) {
        session.error = token.error;
      }
      return session;
    },
  },
});
