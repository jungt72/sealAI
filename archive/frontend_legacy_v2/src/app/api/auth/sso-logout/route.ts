import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { getToken } from "next-auth/jwt";
import { getAuthOptions } from "@/lib/auth-options";
import { getTokens } from "@/lib/auth-token-store";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const issuer = (process.env.KEYCLOAK_ISSUER ?? "").replace(/\/$/, "");
    const base = process.env.NEXTAUTH_URL || req.nextUrl.origin;
    const clientId = process.env.KEYCLOAK_CLIENT_ID!;
    if (!issuer || !clientId) throw new Error("Missing KEYCLOAK_ISSUER or KEYCLOAK_CLIENT_ID");

    const authOptions = await getAuthOptions();
    await getServerSession(authOptions);
    let jwt: any = null;
    try {
      jwt = await getToken({ req });
    } catch {}
    const jti = typeof jwt?.jti === "string" ? jwt.jti : null;
    const stored = jti ? await getTokens(jti) : null;
    const idToken = stored?.idToken ?? null;

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
