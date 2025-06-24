/* eslint-disable no-unused-vars */
import NextAuth from 'next-auth'

declare module 'next-auth' {
  interface Session {
    /** Access-Token (Keycloak / JWT) */
    accessToken?: string
    /** Optional: separat ausgespieltes ID-Token */
    idToken?: string
  }
}
