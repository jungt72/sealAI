// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

const PUBLIC_FILE = /\.(.*)$/;
const SESSION_COOKIES = [
  "__Host-next-auth.session-token",
  "__Secure-authjs.session-token",
  "authjs.session-token",
  "__Secure-next-auth.session-token",
  "next-auth.session-token",
];

const hasSessionCookie = (req: NextRequest) =>
  SESSION_COOKIES.some((n) => !!req.cookies.get(n)?.value);

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/static") ||
    pathname === "/favicon.ico" ||
    PUBLIC_FILE.test(pathname)
  ) return NextResponse.next();

  if (!pathname.startsWith("/dashboard")) return NextResponse.next();

  const hasCookie = hasSessionCookie(req);
  let hasJwt = false;
  try {
    hasJwt = !!(await getToken({ req, secret: process.env.NEXTAUTH_SECRET }));
  } catch {}

  const envBase = (process.env.NEXTAUTH_URL ?? "").replace(/\/+$/, "");
  const base = envBase || `https://${req.headers.get("host")}`;
  const targetPath = `${pathname}${req.nextUrl.search}`;

  if (hasCookie || hasJwt) return NextResponse.next();

  const redirect = new URL("/auth/signin", base);
  redirect.searchParams.set("provider", "keycloak");
  redirect.searchParams.set("callbackUrl", targetPath);
  redirect.searchParams.set("prompt", "login");
  return NextResponse.redirect(redirect);
}

export const config = { matcher: ["/dashboard/:path*"] };
