import { NextRequest, NextResponse } from "next/server";

import { signIn } from "@/auth";

export async function GET(request: NextRequest) {
  const callbackUrl = request.nextUrl.searchParams.get("callbackUrl");
  const redirectTo =
    callbackUrl?.startsWith("/") && !callbackUrl.startsWith("//")
      ? callbackUrl
      : "/dashboard/new";

  await signIn("keycloak", { redirectTo });

  return NextResponse.redirect(new URL(redirectTo, request.url));
}
