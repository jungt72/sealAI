import NextAuth from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

import { singleFlightRefresh } from "@/lib/bff/auth-token";

const KEYCLOAK_ISSUER =
  process.env.KEYCLOAK_ISSUER ?? "https://sealingai.com/realms/sealAI";
const KEYCLOAK_CLIENT_ID =
  process.env.KEYCLOAK_CLIENT_ID ??
  (process.env.NODE_ENV === "production" ? undefined : "nextauth");
const KEYCLOAK_CLIENT_SECRET =
  process.env.KEYCLOAK_CLIENT_SECRET ??
  (process.env.NODE_ENV === "production" ? undefined : "");
const KEYCLOAK_AUTHORIZATION_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/auth`;
const KEYCLOAK_TOKEN_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/token`;
const KEYCLOAK_USERINFO_URL =
  `${KEYCLOAK_ISSUER}/protocol/openid-connect/userinfo`;
const AUTH_SECRET =
  process.env.AUTH_SECRET ??
  process.env.NEXTAUTH_SECRET ??
  (process.env.NODE_ENV === "production"
    ? undefined
    : "sealai-local-development-auth-secret-change-for-production");

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
// NextAuth configuration
// ---------------------------------------------------------------------------
export const { handlers, auth, signIn, signOut } = NextAuth({
  secret: AUTH_SECRET,

  providers: [
    KeycloakProvider({
      clientId: KEYCLOAK_CLIENT_ID as string,
      clientSecret: KEYCLOAK_CLIENT_SECRET as string,

      // Issuer must match the external URL so JWT `iss` validation passes
      issuer: KEYCLOAK_ISSUER,

      wellKnown: undefined, // disable auto-discovery — endpoints are pinned below

      authorization: {
        params: {
          // A refresh_token is issued even without offline_access — it is then an
          // online token bound to the SSO session. offline_access removed because the
          // per-request offline refresh failed ("Session doesn't have required client").
          scope: "openid email profile",
        },
        url: KEYCLOAK_AUTHORIZATION_URL,
      },
      token: KEYCLOAK_TOKEN_URL,
      userinfo: KEYCLOAK_USERINFO_URL,

      checks: ["pkce", "state"],
      allowDangerousEmailAccountLinking:
        process.env.AUTH_ALLOW_DANGEROUS_EMAIL_LINKING === "true",
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

      // Access token expired — attempt a silent, single-flight refresh shared
      // with the BFF path so concurrent refreshes never reuse the same rotating
      // token. On failure, surface the error so the session callback prompts re-login.
      try {
        return await singleFlightRefresh(token);
      } catch {
        return { ...token, error: "RefreshTokenError" };
      }
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
