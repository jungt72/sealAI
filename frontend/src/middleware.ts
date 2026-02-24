import { auth } from "@/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  // Definiere die geschützten Pfade
  const isProtected = pathname.startsWith("/dashboard") || pathname.startsWith("/rag");

  // Wenn der Pfad geschützt ist und der User nicht eingeloggt ist -> Redirect
  if (isProtected && !isLoggedIn) {
    return Response.redirect(new URL("/api/auth/signin", req.nextUrl));
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    /*
     * Optimierter Matcher:
     * Schließt statische Dateien, Bilder und interne Next.js Pfade aus,
     * damit die Middleware nur bei echten Seitenaufrufen feuert.
     */
    "/((?!api/auth|_next/static|_next/image|favicon.ico|public).*)",
  ],
};
