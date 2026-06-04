import { auth } from "@/auth";
import { NextResponse } from "next/server";

import { canonicalizeAppUrl, shouldRedirectToSignIn } from "./proxy-auth";

export const proxy = auth((req) => {
  const canonicalUrl = canonicalizeAppUrl(req.nextUrl);
  if (canonicalUrl) {
    return NextResponse.redirect(canonicalUrl, 308);
  }

  const { pathname } = req.nextUrl;

  if (shouldRedirectToSignIn(pathname, !!req.auth)) {
    const signInUrl = new URL("/login", req.nextUrl);
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
    "/((?!api|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|sitemap-.*\\.xml).*)",
  ],
};
