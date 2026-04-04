import { auth } from "@/auth";
import { NextResponse } from "next/server";

import { shouldRedirectToSignIn } from "./proxy-auth";

export const proxy = auth((req) => {
  const { pathname } = req.nextUrl;

  if (shouldRedirectToSignIn(pathname, !!req.auth)) {
    const signInUrl = new URL("/api/auth/signin", req.nextUrl);
    signInUrl.searchParams.set(
      "callbackUrl",
      req.nextUrl.pathname + req.nextUrl.search,
    );
    return Response.redirect(signInUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|public).*)",
  ],
};
