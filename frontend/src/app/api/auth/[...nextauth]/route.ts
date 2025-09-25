import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },

  providers: [
    KeycloakProvider({
      issuer: process.env.KEYCLOAK_ISSUER,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET || "dummy",
      authorization: { params: { scope: "openid profile email" } },
    }),
  ],

  callbacks: {
    // legt das access/id/refresh token beim ersten Login in den JWT und erneuert es ggf.
    async jwt({ token, account }) {
      if (account) {
        (token as any).accessToken  = (account as any).access_token ?? null;
        (token as any).idToken      = (account as any).id_token ?? null;
        (token as any).refreshToken = (account as any).refresh_token ?? null;
        (token as any).expires_at   = (account as any).expires_at ?? null; // epoch seconds
      }
      return token;
    },

    // macht Tokens in der Client-Session verfügbar
    async session({ session, token }) {
      (session as any).accessToken = (token as any).accessToken ?? null;
      (session as any).idToken     = (token as any).idToken ?? null;
      (session as any).expires_at  = (token as any).expires_at ?? null;
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
