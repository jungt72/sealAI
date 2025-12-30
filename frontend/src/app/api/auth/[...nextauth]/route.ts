import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";
import { isRefreshTokenExpired, isTokenExpired, refreshAccessToken } from "@/lib/keycloak-refresh";

const normalizeExpires = (value: string | number | null | undefined): number | null => {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const SESSION_MAX_AGE_SECONDS = 1800;
const SESSION_UPDATE_AGE_SECONDS = 300;

export const authOptions: NextAuthOptions = {
  // Keep session/jwt lifetimes explicit to avoid ghost sessions when SSO expires.
  session: { strategy: "jwt", maxAge: SESSION_MAX_AGE_SECONDS, updateAge: SESSION_UPDATE_AGE_SECONDS },
  jwt: { maxAge: SESSION_MAX_AGE_SECONDS },

  providers: [
    KeycloakProvider({
      issuer: process.env.KEYCLOAK_ISSUER,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET || "dummy",
      authorization: { params: { scope: "openid profile email offline_access" } },
    }),
  ],

  callbacks: {
    // legt das access/id/refresh token beim ersten Login in den JWT
    async jwt({ token, account }) {
      if (account) {
        const expiresAt = normalizeExpires((account as any).expires_at ?? null);
        const refreshExpiresIn = normalizeExpires(
          (account as any).refresh_expires_in ?? (account as any).refresh_token_expires_in ?? null,
        );
        const now = Math.floor(Date.now() / 1000);
        const refreshExpiresAt =
          typeof refreshExpiresIn === "number" && refreshExpiresIn > 0
            ? now + refreshExpiresIn
            : now + SESSION_MAX_AGE_SECONDS;
        (token as any).accessToken = (account as any).access_token ?? null;
        (token as any).idToken = (account as any).id_token ?? null;
        (token as any).refreshToken = (account as any).refresh_token ?? null;
        (token as any).expires_at = expiresAt;
        (token as any).accessTokenExpires = expiresAt;
        (token as any).refreshTokenExpires = refreshExpiresAt;
        (token as any).error = null;
      }

      if ((token as any).error === "RefreshAccessTokenError") {
        return token;
      }

      if ((token as any).refreshToken && isRefreshTokenExpired((token as any).refreshTokenExpires)) {
        return {
          ...token,
          accessToken: null,
          refreshToken: null,
          idToken: null,
          expires_at: null,
          accessTokenExpires: null,
          refreshTokenExpires: null,
          error: "RefreshTokenExpired",
        } as typeof token;
      }

      if (isTokenExpired((token as any).expires_at) && !(token as any).refreshToken) {
        console.warn("Keycloak refresh token missing while access token expired.");
        return {
          ...token,
          accessToken: null,
          refreshToken: null,
          idToken: null,
          expires_at: null,
          accessTokenExpires: null,
          refreshTokenExpires: null,
          error: "RefreshTokenMissing",
        } as typeof token;
      }

      if (isTokenExpired((token as any).expires_at) && (token as any).refreshToken) {
        return refreshAccessToken(token as any);
      }

      return token;
    },

    // macht Tokens in der Client-Session verfügbar
    async session({ session, token }) {
      (session as any).accessToken = (token as any).accessToken ?? null;
      (session as any).idToken = (token as any).idToken ?? null;
      (session as any).expires_at = (token as any).expires_at ?? null;
      (session as any).error = (token as any).error ?? null;
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
