import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

export async function middleware(req: NextRequest) {
  const token = await getToken({ req });
  if (!token) {
    const baseUrl = process.env.NEXTAUTH_URL || req.nextUrl.origin;
    const callbackUrl = encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search);
    // direkt Keycloak-Provider nutzen (spart eine Seite)
    return NextResponse.redirect(
      `${baseUrl}/api/auth/signin/keycloak?callbackUrl=${callbackUrl}`
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/protected/:path*"],
};
