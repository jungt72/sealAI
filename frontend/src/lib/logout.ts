"use client"

import { signOut } from "next-auth/react"

export const handleLogout = async (idToken?: string) => {
  const redirectUri = encodeURIComponent("https://sealai.net")

  // Local session cleanup
  await signOut({ redirect: false })

  // Redirect to Keycloak logout
  const logoutUrl = idToken
    ? `https://auth.sealai.net/realms/sealAI/protocol/openid-connect/logout?id_token_hint=${idToken}&post_logout_redirect_uri=${redirectUri}`
    : `/api/auth/custom-logout`

  window.location.href = logoutUrl
}
