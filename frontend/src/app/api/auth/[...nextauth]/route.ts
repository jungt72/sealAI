import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

function must(v: string | undefined, fallback: string): string {
  const s = (v ?? "").trim().replace(/\/+$/, "");
  if (!s || s === "http://localhost" || s === "https://localhost") return fallback;
  return s;
}

const ISSUER = must(process.env.KEYCLOAK_ISSUER, "https://auth.sealai.net/realms/sealAI");
const NEXTAUTH_URL = must(process.env.NEXTAUTH_URL, "https://sealai.net");

async function refreshAccessToken(token: any) {
  try {
    const url = `${ISSUER}/protocol/openid-connect/token`;
    const form = new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: token.refreshToken,
      client_id: process.env.KEYCLOAK_CLIENT_ID as string,
    });
    if (process.env.KEYCLOAK_CLIENT_SECRET) form.set("client_secret", process.env.KEYCLOAK_CLIENT_SECRET);
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: form });
    const refreshed = await res.json();
    if (!res.ok) throw new Error(refreshed?.error_description || "refresh_failed");
    return {
      ...token,
      accessToken: refreshed.access_token,
      accessTokenExpires: Date.now() + (refreshed.expires_in ?? 60) * 1000,
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
      idToken: refreshed.id_token ?? token.idToken,
      error: undefined,
    };
  } catch {
    return { ...token, error: "RefreshAccessTokenError" };
  }
}

const authOptions: NextAuthOptions = {
  secret: process.env.NEXTAUTH_SECRET,
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 },
  providers: [
    KeycloakProvider({
      issuer: ISSUER,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      authorization: { params: { scope: "openid email profile" } },
      profile(p) {
        return {
          id: p.sub,
          name: p.name || `${p.given_name ?? ""} ${p.family_name ?? ""}`.trim() || p.preferred_username,
          email: p.email,
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        (token as any).accessToken = account.access_token;
        (token as any).accessTokenExpires = account.expires_at ? account.expires_at * 1000 : Date.now() + 60 * 1000;
        (token as any).refreshToken = account.refresh_token;
        (token as any).idToken = (account as any).id_token;
        return token;
      }
      const exp = (token as any).accessTokenExpires as number | undefined;
      if (exp && Date.now() < exp - 30_000) return token;
      return await refreshAccessToken(token);
    },
    async session({ session, token }) {
      (session as any).accessToken = (token as any).accessToken;
      (session as any).accessTokenExpires = (token as any).accessTokenExpires;
      (session as any).idToken = (token as any).idToken;
      (session as any).error = (token as any).error;
      return session;
    },
    async redirect({ url, baseUrl }) {
      try { const u = new URL(url); if (u.origin === baseUrl) return url; } catch {}
      return `${NEXTAUTH_URL}/dashboard`;
    },
  },
  pages: { error: "/auth/error" },
  debug: process.env.NODE_ENV !== "production",
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
