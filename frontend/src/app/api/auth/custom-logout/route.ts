import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  // Legacy-Route -> auf neue SSO-Logout-Route umleiten
  const base = process.env.NEXTAUTH_URL || req.nextUrl.origin;
  return NextResponse.redirect(`${base}/api/auth/sso-logout`);
}

export const dynamic = "force-dynamic";
