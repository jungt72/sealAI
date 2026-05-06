import { auth } from "@/auth";
import { NextResponse } from "next/server";

import { shouldRedirectToSignIn } from "./proxy-auth";

export const proxy = auth((req) => {
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
    "/dashboard/:path*",
    "/goal/:path*",
    "/goal",
    "/rag/:path*",
  ],
};
