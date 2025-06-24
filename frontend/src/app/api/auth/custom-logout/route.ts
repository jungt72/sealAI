import { NextResponse } from "next/server"

export async function GET() {
  const redirectUri = encodeURIComponent("https://sealai.net")
  const logoutUrl = `https://auth.sealai.net/realms/sealAI/protocol/openid-connect/logout?post_logout_redirect_uri=${redirectUri}`

  const response = NextResponse.redirect(logoutUrl)

  const cookiesToClear = [
    "next-auth.session-token",
    "__Secure-next-auth.session-token",
    "next-auth.callback-url",
    "next-auth.csrf-token"
  ]

  for (const cookie of cookiesToClear) {
    response.cookies.set(cookie, "", {
      path: "/",
      maxAge: 0
    })
  }

  return response
}
