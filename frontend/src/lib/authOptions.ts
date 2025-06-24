// frontend/src/lib/authOptions.ts

import KeycloakProvider from "next-auth/providers/keycloak"
import { NextAuthOptions } from "next-auth"

export const authOptions: NextAuthOptions = {
  providers: [
    KeycloakProvider({
      issuer: process.env.BACKEND_KEYCLOAK_ISSUER!,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      wellKnown: `${process.env.BACKEND_KEYCLOAK_ISSUER!}/.well-known/openid-configuration`,
    }),
  ],
  session: {
    strategy: "jwt",
  },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) {
        token.accessToken = account.access_token
      }
      if (account?.id_token) {
        token.idToken = account.id_token
      }
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string
      session.idToken = token.idToken as string
      return session
    },
  },
}

