import { NextRequest, NextResponse } from "next/server";

import { handlers } from "@/auth";
import { expiredKeycloakRecoveryUrl } from "@/lib/auth/recovery";

export async function GET(request: NextRequest) {
  const recoveryUrl = expiredKeycloakRecoveryUrl(new URL(request.url));
  if (recoveryUrl) {
    return NextResponse.redirect(recoveryUrl, 302);
  }
  return handlers.GET(request);
}

export const POST = handlers.POST;
