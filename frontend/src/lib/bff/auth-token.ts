import type { JWT } from "next-auth/jwt";
import { getToken } from "next-auth/jwt";

import { BffError } from "./errors.ts";

function resolveAuthSecret(): string {
  const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
  if (!secret) {
    throw new BffError("Auth secret is not configured.", 500);
  }
  return secret;
}

function shouldUseSecureCookies(request: Request): boolean {
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) {
    return forwardedProto.split(",")[0]?.trim() === "https";
  }

  return new URL(request.url).protocol === "https:";
}

function extractAccessToken(token: JWT | string | null): string | null {
  if (!token || typeof token === "string") {
    return null;
  }

  return typeof token.accessToken === "string" && token.accessToken
    ? token.accessToken
    : null;
}

export async function getAccessToken(request: Request): Promise<string> {
  const token = await getToken({
    req: request,
    secret: resolveAuthSecret(),
    secureCookie: shouldUseSecureCookies(request),
  });
  const accessToken = extractAccessToken(token as JWT | string | null);

  if (!accessToken) {
    throw new BffError("Unauthorized", 401);
  }

  return accessToken;
}
