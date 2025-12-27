"use client"

import { signOut } from "next-auth/react"

const CLIENT_ID =
  process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ||
  process.env.KEYCLOAK_CLIENT_ID ||
  "nextauth"

const ISSUER =
  process.env.NEXT_PUBLIC_KEYCLOAK_ISSUER ||
  process.env.KEYCLOAK_ISSUER ||
  "https://auth.sealai.net/realms/sealAI"

export const logout = async (idToken?: string, redirectTo = "/") => {
  const origin = typeof window !== "undefined" ? window.location.origin : ""
  const safePath = redirectTo.startsWith("/") ? redirectTo : "/"
  const postLogout = `${origin}${safePath}`

  // 1) lokale NextAuth-Session beenden
  await signOut({ redirect: false })

  // 2) RP-initiated logout URL bauen
  const base = `${ISSUER}/protocol/openid-connect/logout`
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    post_logout_redirect_uri: postLogout,
  })

  // Nur ein id_token_hint mitsenden, wenn wirklich vorhanden
  if (idToken && idToken.split(".").length === 3) {
    params.set("id_token_hint", idToken)
  }

  // 3) Browser zu Keycloak umleiten
  window.location.href = `${base}?${params.toString()}`
}

// Alias für alte Importe
export const handleLogout = logout
