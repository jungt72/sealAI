// frontend/src/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

const PUBLIC_FILE = /\.(.*)$/;

// NextAuth v4/v5 mögliche Session-Cookies
const SESSION_COOKIES = [
  "__Secure-authjs.session-token",
  "authjs.session-token",
  "__Secure-next-auth.session-token",
  "next-auth.session-token",
];

function hasSessionCookie(req: NextRequest) {
  return SESSION_COOKIES.some((n) => !!req.cookies.get(n)?.value);
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // nie abfangen
  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/static") ||
    pathname === "/favicon.ico" ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }

  // schneller Cookie-Check
  const hasCookie = hasSessionCookie(req);

  // zusätzlich JWT prüfen (falls SECRET passt)
  let hasJwt = false;
  try {
    const tok = await getToken({ req });
    hasJwt = !!tok;
  } catch {
    // ignore
  }

  if (hasCookie || hasJwt) return NextResponse.next();

  // nicht eingeloggt -> Keycloak-Login ERZWINGEN (prompt=login)
  const url = req.nextUrl.clone();
  const base = process.env.NEXTAUTH_URL ?? `${url.protocol}//${url.host}`;
  const redirect = new URL("/api/auth/signin/keycloak", base);
  redirect.searchParams.set("callbackUrl", url.pathname + url.search);
  redirect.searchParams.set("prompt", "login"); // wichtig: kein stilles SSO

  return NextResponse.redirect(redirect);
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
