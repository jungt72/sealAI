import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";
import { isTokenExpired, refreshAccessToken } from "@/lib/keycloak-refresh";

const normalizeExpires = (value: string | number | null | undefined): number | null => {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },

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
        (token as any).accessToken = (account as any).access_token ?? null;
        (token as any).idToken = (account as any).id_token ?? null;
        (token as any).refreshToken = (account as any).refresh_token ?? null;
        (token as any).expires_at = normalizeExpires((account as any).expires_at ?? null);
        (token as any).error = null;
      }

      if ((token as any).error === "RefreshAccessTokenError") {
        return token;
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
