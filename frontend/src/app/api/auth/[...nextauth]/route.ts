import { NextRequest, NextResponse } from "next/server";

import { handlers } from "@/auth";
import { expiredKeycloakRecoveryUrl } from "@/lib/auth/recovery";

export async function GET(request: NextRequest) {
  // `request.url` carries Next's internal container origin behind nginx (`0.0.0.0:3000`). Use the
  // deployment-owned public origin so the recovery Location header can never leak an unreachable
  // Docker address. NEXTAUTH_URL is required by docker-compose.deploy.yml in production.
  const publicOrigin = process.env.NEXTAUTH_URL ?? request.nextUrl.origin;
  const recoveryUrl = expiredKeycloakRecoveryUrl(new URL(request.url), publicOrigin);
  if (recoveryUrl) {
    return NextResponse.redirect(recoveryUrl, 302);
  }
  return handlers.GET(request);
}

export const POST = handlers.POST;
