import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
import { getTokens } from "@/lib/auth-token-store";

export type AuthReason = "no_session" | "no_jwt" | "no_access_token" | "refresh_failed";

export type AuthResult = {
  token: any | null;
  accessToken: string | null;
  userId: string | null;
  reason?: AuthReason;
  debug?: Record<string, unknown>;
};

const SESSION_COOKIES = [
  "__Host-next-auth.session-token",
  "__Secure-authjs.session-token",
  "authjs.session-token",
  "__Secure-next-auth.session-token",
  "next-auth.session-token",
];

const REFRESH_ERRORS = new Set(["RefreshAccessTokenError", "RefreshTokenExpired", "RefreshTokenMissing"]);

const hasSessionCookie = (req: NextRequest) =>
  SESSION_COOKIES.some((name) => Boolean(req.cookies.get(name)?.value));

const wantsDebug = (req: NextRequest) =>
  process.env.AUTH_DEBUG === "true" || req.nextUrl.searchParams.get("debug") === "1";

export const getRequestAuth = async (
  req: NextRequest,
  options?: { useRedis?: boolean; requireAccessToken?: boolean; logContext?: string },
): Promise<AuthResult> => {
  const useRedis = options?.useRedis ?? true;
  const requireAccessToken = options?.requireAccessToken ?? true;
  const logContext = options?.logContext ?? "auth";
  const hasCookie = hasSessionCookie(req);
  const debugOn = wantsDebug(req);

  let jwt: any = null;
  try {
    jwt = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
  } catch {}

  if (!jwt) {
    const reason: AuthReason = hasCookie ? "no_jwt" : "no_session";
    if (debugOn) {
      console.warn(`[${logContext}] missing jwt`, { hasCookie });
    }
    return {
      token: null,
      accessToken: null,
      userId: null,
      reason,
      debug: debugOn ? { hasCookie } : undefined,
    };
  }

  const tokenError = typeof jwt?.error === "string" ? jwt.error : null;
  const jti = typeof jwt?.jti === "string" ? jwt.jti : null;
  const userId = typeof jwt?.sub === "string" ? jwt.sub : null;

  let accessToken =
    typeof jwt?.accessToken === "string"
      ? jwt.accessToken
      : typeof jwt?.access_token === "string"
        ? jwt.access_token
        : null;

  let redisHit = false;
  if (!accessToken && useRedis && jti) {
    const stored = await getTokens(jti);
    if (stored?.accessToken) {
      accessToken = stored.accessToken;
      redisHit = true;
    }
  }

  if (!accessToken && REFRESH_ERRORS.has(tokenError || "")) {
    if (debugOn) {
      console.warn(`[${logContext}] refresh error`, { tokenError });
    }
    return {
      token: jwt,
      accessToken: null,
      userId,
      reason: "refresh_failed",
      debug: debugOn ? { hasCookie, tokenError } : undefined,
    };
  }

  if (requireAccessToken && !accessToken) {
    if (debugOn) {
      console.warn(`[${logContext}] missing access token`, { jti: Boolean(jti) });
    }
    return {
      token: jwt,
      accessToken: null,
      userId,
      reason: "no_access_token",
      debug: debugOn ? { hasCookie, jti: Boolean(jti) } : undefined,
    };
  }

  if (debugOn) {
    console.warn(`[${logContext}] auth ok`, {
      hasCookie,
      hasJwt: Boolean(jwt),
      hasSub: Boolean(userId),
      hasJti: Boolean(jti),
      hasAccessToken: Boolean(accessToken),
      redisHit,
      tokenError,
    });
  }

  return {
    token: jwt,
    accessToken,
    userId,
    debug: debugOn
      ? {
          hasCookie,
          hasJwt: Boolean(jwt),
          hasSub: Boolean(userId),
          hasJti: Boolean(jti),
          hasAccessToken: Boolean(accessToken),
          redisHit,
          tokenError,
        }
      : undefined,
  };
};
