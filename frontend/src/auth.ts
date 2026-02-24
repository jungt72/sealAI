import NextAuth from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

/*
  Split-DNS Strategy (Final Hardcoded Fix):
  - Authorization: External URL (Browser -> Nginx -> Keycloak)
  - Token/UserInfo: Internal Docker URL (Frontend -> Keycloak:8080)
*/

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    KeycloakProvider({
      clientId: process.env.KEYCLOAK_CLIENT_ID as string,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET as string,
      
      // Issuer must match external URL for JWT validation
      issuer: "https://auth.sealai.net/realms/sealAI",
      
      wellKnown: undefined, // DISABLE auto-discovery
      
      authorization: {
        params: {
          scope: "openid email profile",
        },
        url: "https://auth.sealai.net/realms/sealAI/protocol/openid-connect/auth",
      },
      token: "http://keycloak:8080/realms/sealAI/protocol/openid-connect/token",
      userinfo: "http://keycloak:8080/realms/sealAI/protocol/openid-connect/userinfo",
      
      checks: ["pkce", "state"],
      allowDangerousEmailAccountLinking: true, 
    }),
  ],
  trustHost: true,
  callbacks: {
    async session({ session, token }) {
      if (token.accessToken) {
        (session as any).accessToken = token.accessToken;
      }
      if (token.idToken) {
        (session as any).idToken = token.idToken;
      }
      return session;
    },
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
        token.idToken = account.id_token;
      }
      return token;
    }
  },
});
