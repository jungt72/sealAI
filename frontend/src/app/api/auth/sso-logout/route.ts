import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const issuer = (process.env.KEYCLOAK_ISSUER ?? "").replace(/\/$/, "");
  const baseUrl = process.env.NEXTAUTH_URL || req.nextUrl.origin;
  const clientId = process.env.KEYCLOAK_CLIENT_ID;

  if (!issuer) {
    return NextResponse.json({ error: "Missing KEYCLOAK_ISSUER" }, { status: 500 });
  }

  const jwt = (await getToken({ req })) as any;
  const idToken = jwt?.idToken || jwt?.id_token;

  const endSession = new URL(`${issuer}/protocol/openid-connect/logout`);
  endSession.searchParams.set("post_logout_redirect_uri", baseUrl);
  if (idToken) endSession.searchParams.set("id_token_hint", idToken);
  if (clientId) endSession.searchParams.set("client_id", clientId);

  return NextResponse.json({ logoutUrl: endSession.toString() });
}
