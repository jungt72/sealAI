// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

const PUBLIC_FILE = /\.(.*)$/;
const SESSION_COOKIES = [
  "__Secure-authjs.session-token","authjs.session-token",
  "__Secure-next-auth.session-token","next-auth.session-token"
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
    hasJwt = !!(await getToken({ req }));
  } catch {}

  const envBase = (process.env.NEXTAUTH_URL ?? "").replace(/\/+$/, "");
  const base = envBase || `https://${req.headers.get("host")}`;
  const chatId = req.nextUrl.searchParams.get("chat_id");
  const targetPath = chatId ? `/chat/${encodeURIComponent(chatId)}` : "/chat";
  const targetUrl = `${base}${targetPath}`;

  if (hasCookie || hasJwt) {
    const currentPathWithQuery = `${req.nextUrl.pathname}${req.nextUrl.search}`;
    if (currentPathWithQuery !== targetPath) {
      return NextResponse.redirect(targetUrl);
    }
    return NextResponse.next();
  }

  const redirect = new URL("/api/auth/signin", base);
  redirect.searchParams.set("provider", "keycloak");
  redirect.searchParams.set("callbackUrl", targetUrl);
  redirect.searchParams.set("prompt", "login");
  return NextResponse.redirect(redirect);
}

export const config = { matcher: ["/dashboard/:path*"] };
