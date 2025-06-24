// frontend/src/app/api/auth/[...nextauth]/route.ts
import NextAuth, { type NextAuthOptions } from 'next-auth'
import Keycloak from 'next-auth/providers/keycloak'

const authOptions: NextAuthOptions = {
  providers: [
    Keycloak({
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      issuer: process.env.KEYCLOAK_ISSUER!,
      wellKnown: `${process.env.KEYCLOAK_ISSUER!}/.well-known/openid-configuration`,
    }),
  ],

  // pages: { signIn: '/auth/signin', error: '/auth/error' },  // <---- Diese Zeile AUSKOMMENTIEREN oder löschen
  pages: { error: '/auth/error' }, // Fehlerseite bleibt erlaubt

  session: { strategy: 'jwt', maxAge: 24 * 60 * 60 },
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token
        token.idToken = account.id_token
      }
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string | undefined
      session.idToken = token.idToken as string | undefined
      return session
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }

