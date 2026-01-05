import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const issuer = (process.env.KEYCLOAK_ISSUER ?? "").replace(/\/$/, "");
    const base = process.env.NEXTAUTH_URL || req.nextUrl.origin;
    const clientId = process.env.KEYCLOAK_CLIENT_ID!;
    if (!issuer || !clientId) throw new Error("Missing KEYCLOAK_ISSUER or KEYCLOAK_CLIENT_ID");

    const jwt = (await getToken({ req }).catch(() => null)) as any;
    const idToken = jwt?.idToken;

    // Nach Keycloak-Logout auf Seite leiten, die NextAuth signOut automatisch POSTet
    const postLogout = new URL("/auth/signed-out", base);

    const url = new URL(`${issuer}/protocol/openid-connect/logout`);
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("post_logout_redirect_uri", postLogout.toString());
    if (idToken) url.searchParams.set("id_token_hint", idToken);

    return NextResponse.redirect(url.toString());
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "logout_build_failed" }, { status: 500 });
  }
}

// Akzeptiere POST ebenfalls
export const POST = GET;
