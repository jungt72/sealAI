import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

const normalizedBaseUrl =
  (process.env.NEXTAUTH_URL || process.env.NEXT_PUBLIC_SITE_URL || "")
    .replace(/\/$/, "");

const defaultRedirectUri = normalizedBaseUrl
  ? `${normalizedBaseUrl}/api/auth/callback/keycloak`
  : undefined;

const keycloakAuthorizationParams: Record<string, string> = {
  scope: "openid profile email",
};

if (defaultRedirectUri) {
  keycloakAuthorizationParams.redirect_uri = defaultRedirectUri;
}

const kcIdpHint =
  process.env.KEYCLOAK_IDP_HINT || process.env.NEXT_PUBLIC_KEYCLOAK_IDP_HINT;
if (kcIdpHint) {
  keycloakAuthorizationParams.kc_idp_hint = kcIdpHint;
}

if ((process.env.KEYCLOAK_PROMPT_LOGIN || "").toLowerCase() === "true") {
  keycloakAuthorizationParams.prompt = "login";
}

const issuer = process.env.KEYCLOAK_ISSUER
  ? process.env.KEYCLOAK_ISSUER.replace(/\/$/, "")
  : undefined;

const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },

  providers: [
    KeycloakProvider({
      issuer,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET || "dummy",
      authorization: { params: keycloakAuthorizationParams },
    }),
  ],

  callbacks: {
    // legt das access/id/refresh token beim ersten Login in den JWT und erneuert es ggf.
    async jwt({ token, account }) {
      if (account) {
        (token as any).accessToken = (account as any).access_token ?? null;
        (token as any).idToken = (account as any).id_token ?? null;
        (token as any).refreshToken = (account as any).refresh_token ?? null;
        (token as any).expires_at = (account as any).expires_at ?? null; // epoch seconds
      }
      return token;
    },

    // macht Tokens in der Client-Session verfügbar
    async session({ session, token }) {
      (session as any).accessToken = (token as any).accessToken ?? null;
      (session as any).idToken = (token as any).idToken ?? null;
      (session as any).expires_at = (token as any).expires_at ?? null;
      return session;
    },

    async redirect({ url, baseUrl }) {
      const normalizedBase = (normalizedBaseUrl || baseUrl).replace(/\/$/, "");
      const defaultTarget = `${normalizedBase}/dashboard`;

      const enforceDashboard = (target: URL) => {
        if (target.pathname === "/" || target.pathname === "/auth/signin") {
          target.pathname = "/dashboard";
          target.search = "";
          target.hash = "";
        }
        return target;
      };

      try {
        if (url.startsWith("/")) {
          const target = new URL(`${normalizedBase}${url}`);
          return enforceDashboard(target).toString();
        }

        const target = new URL(url);
        if (target.origin.replace(/\/$/, "") !== normalizedBase) {
          return defaultTarget;
        }
        return enforceDashboard(target).toString();
      } catch {
        try {
          const target = new URL(url, normalizedBase);
          return enforceDashboard(target).toString();
        } catch {
          return defaultTarget;
        }
      }
    },
  },

  pages: {
    signIn: "/auth/signin",
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
