import type { AuthOptions } from 'next-auth'
import KeycloakProvider     from 'next-auth/providers/keycloak'

/**
 * Zentrale Next-Auth-Konfiguration (App-Router-Variante).
 * - session:   JWT-basierte Sessions
 * - providers: Keycloak-OIDC
 * - callbacks: legt das Access-Token in `session.accessToken` ab,
 *              damit der Client es für den WebSocket nutzen kann.
 */
export const authOptions: AuthOptions = {
  session: { strategy: 'jwt' },

  providers: [
    KeycloakProvider({
      clientId:     process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      issuer:       process.env.KEYCLOAK_ISSUER!,
    }),
  ],

  callbacks: {
    async session({ session, token }) {
      if (token.access_token) session.accessToken = token.access_token as string
      return session
    },
    async jwt({ token, account }) {
      if (account?.access_token) token.access_token = account.access_token
      return token
    },
  },
}
