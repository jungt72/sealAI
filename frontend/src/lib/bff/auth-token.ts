import type { JWT } from "next-auth/jwt";
import { encode, getToken } from "next-auth/jwt";

import { BffError } from "./errors.ts";

const ACCESS_TOKEN_REFRESH_BUFFER_MS = 30_000;
const SESSION_COOKIE_CHUNK_SIZE = 3_800;
const DEFAULT_SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
const AUTHJS_SESSION_COOKIE = "authjs.session-token";
const LEGACY_NEXTAUTH_SESSION_COOKIE = "next-auth.session-token";

type BffCookieOptions = {
  httpOnly: boolean;
  sameSite: "lax";
  secure: boolean;
  path: string;
  maxAge: number;
};

export type BffCookieUpdate = {
  name: string;
  value: string;
  options: BffCookieOptions;
};

export type BffAccessTokenResult = {
  accessToken: string;
  cookieUpdates: BffCookieUpdate[];
};

type CookieWritableResponse = {
  cookies: {
    set: (name: string, value: string, options: BffCookieOptions) => void;
  };
};

function resolveAuthSecret(): string {
  const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
  if (!secret) {
    throw new BffError("Auth secret is not configured.", 500);
  }
  return secret;
}

function resolveKeycloakTokenUrl(): string {
  const issuer = process.env.KEYCLOAK_ISSUER || "https://sealingai.com/realms/sealAI";
  return `${issuer.replace(/\/$/, "")}/protocol/openid-connect/token`;
}

function resolveKeycloakClientId(): string {
  const clientId = process.env.KEYCLOAK_CLIENT_ID || "nextauth";
  if (!clientId) {
    throw new BffError("Keycloak client id is not configured.", 500);
  }
  return clientId;
}

function resolveKeycloakClientSecret(): string {
  const clientSecret = process.env.KEYCLOAK_CLIENT_SECRET || "";
  if (process.env.NODE_ENV === "production" && !clientSecret) {
    throw new BffError("Keycloak client secret is not configured.", 500);
  }
  return clientSecret;
}

function shouldUseSecureCookies(request: Request): boolean {
  const cookieNames = requestCookieNames(request);
  if (
    cookieNames.has("__Secure-authjs.session-token") ||
    cookieNames.has("__Secure-next-auth.session-token") ||
    [...cookieNames].some(
      (name) =>
        name.startsWith("__Secure-authjs.session-token.") ||
        name.startsWith("__Secure-next-auth.session-token."),
    )
  ) {
    return true;
  }

  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) {
    return forwardedProto.split(",")[0]?.trim() === "https";
  }

  return new URL(request.url).protocol === "https:";
}

function sessionCookieName(secureCookie: boolean): string {
  return secureCookie ? `__Secure-${AUTHJS_SESSION_COOKIE}` : AUTHJS_SESSION_COOKIE;
}

function legacySessionCookieName(secureCookie: boolean): string {
  return secureCookie
    ? `__Secure-${LEGACY_NEXTAUTH_SESSION_COOKIE}`
    : LEGACY_NEXTAUTH_SESSION_COOKIE;
}

function requestCookieNames(request: Request): Set<string> {
  const header = request.headers.get("cookie") || "";
  const names = new Set<string>();
  for (const part of header.split(";")) {
    const [rawName] = part.trim().split("=");
    if (rawName) {
      names.add(rawName);
    }
  }
  return names;
}

function chunkSessionCookie(cookieName: string, value: string): Array<{ name: string; value: string }> {
  if (value.length <= SESSION_COOKIE_CHUNK_SIZE) {
    return [{ name: cookieName, value }];
  }

  const chunks: Array<{ name: string; value: string }> = [];
  for (let offset = 0; offset < value.length; offset += SESSION_COOKIE_CHUNK_SIZE) {
    chunks.push({
      name: `${cookieName}.${chunks.length}`,
      value: value.slice(offset, offset + SESSION_COOKIE_CHUNK_SIZE),
    });
  }
  return chunks;
}

function hasCookieFamily(cookieNames: Set<string>, cookieName: string): boolean {
  return cookieNames.has(cookieName) || [...cookieNames].some((name) => name.startsWith(`${cookieName}.`));
}

function candidateSessionCookieNames(request: Request, secureCookie: boolean): string[] {
  const cookieNames = requestCookieNames(request);
  const candidates = [
    sessionCookieName(secureCookie),
    legacySessionCookieName(secureCookie),
    sessionCookieName(!secureCookie),
    legacySessionCookieName(!secureCookie),
  ];
  return candidates.filter((cookieName, index) => {
    if (candidates.indexOf(cookieName) !== index) {
      return false;
    }
    if (index === 0) {
      return true;
    }
    return hasCookieFamily(cookieNames, cookieName);
  });
}

async function readSessionJwt(request: Request, secureCookie: boolean): Promise<JWT | null> {
  for (const cookieName of candidateSessionCookieNames(request, secureCookie)) {
    const token = await getToken({
      req: request,
      secret: resolveAuthSecret(),
      secureCookie: cookieName.startsWith("__Secure-"),
      cookieName,
      salt: cookieName,
    });
    if (token && typeof token !== "string") {
      return token;
    }
  }
  return null;
}

function extractAccessToken(token: JWT | string | null): string | null {
  if (!token || typeof token === "string") {
    return null;
  }

  return typeof token.accessToken === "string" && token.accessToken
    ? token.accessToken
    : null;
}

function tokenExpiresAtMs(token: JWT): number {
  const expiresAt = token.expiresAt;
  return typeof expiresAt === "number" && Number.isFinite(expiresAt) ? expiresAt * 1000 : 0;
}

function hasUsableAccessToken(token: JWT): boolean {
  return Boolean(extractAccessToken(token)) && Date.now() < tokenExpiresAtMs(token) - ACCESS_TOKEN_REFRESH_BUFFER_MS;
}

async function refreshBffAccessToken(token: JWT): Promise<JWT> {
  const refreshToken =
    typeof token.refreshToken === "string" && token.refreshToken ? token.refreshToken : null;
  if (!refreshToken) {
    throw new BffError("Unauthorized", 401);
  }

  const response = await fetch(resolveKeycloakTokenUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: resolveKeycloakClientId(),
      client_secret: resolveKeycloakClientSecret(),
      refresh_token: refreshToken,
    }),
    cache: "no-store",
  });

  const refreshed = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok || typeof refreshed.access_token !== "string") {
    throw new BffError("Unauthorized", 401);
  }

  const expiresIn =
    typeof refreshed.expires_in === "number" && Number.isFinite(refreshed.expires_in)
      ? refreshed.expires_in
      : 300;

  return {
    ...token,
    accessToken: refreshed.access_token,
    idToken: typeof refreshed.id_token === "string" ? refreshed.id_token : token.idToken,
    refreshToken:
      typeof refreshed.refresh_token === "string" && refreshed.refresh_token
        ? refreshed.refresh_token
        : token.refreshToken,
    expiresAt: Math.floor(Date.now() / 1000) + expiresIn,
    error: undefined,
  };
}

async function refreshedJwtCookieUpdates(request: Request, token: JWT): Promise<BffCookieUpdate[]> {
  const secureCookie = shouldUseSecureCookies(request);
  const cookieName = sessionCookieName(secureCookie);
  const maxAge = Number(process.env.AUTH_SESSION_MAX_AGE_SECONDS || DEFAULT_SESSION_MAX_AGE_SECONDS);
  const options: BffCookieOptions = {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookie,
    path: "/",
    maxAge,
  };
  const value = await encode({
    secret: resolveAuthSecret(),
    salt: cookieName,
    token,
    maxAge,
  });
  const chunks = chunkSessionCookie(cookieName, value);
  const nextNames = new Set(chunks.map((chunk) => chunk.name));
  const staleNames = [...requestCookieNames(request)].filter(
    (name) => name === cookieName || name.startsWith(`${cookieName}.`),
  );
  const updates: BffCookieUpdate[] = chunks.map((chunk) => ({
    ...chunk,
    options,
  }));

  for (const staleName of staleNames) {
    if (!nextNames.has(staleName)) {
      updates.push({
        name: staleName,
        value: "",
        options: { ...options, maxAge: 0 },
      });
    }
  }

  if (chunks.length > 1 && !staleNames.includes(cookieName)) {
    updates.push({
      name: cookieName,
      value: "",
      options: { ...options, maxAge: 0 },
    });
  }

  return updates;
}

export function applyBffCookieUpdates(
  response: CookieWritableResponse,
  updates: BffCookieUpdate[],
): void {
  for (const update of updates) {
    response.cookies.set(update.name, update.value, update.options);
  }
}

export async function getAccessTokenResult(request: Request): Promise<BffAccessTokenResult> {
  const secureCookie = shouldUseSecureCookies(request);
  const token = await readSessionJwt(request, secureCookie);
  if (!token) {
    throw new BffError("Unauthorized", 401);
  }

  if (hasUsableAccessToken(token)) {
    return {
      accessToken: extractAccessToken(token) as string,
      cookieUpdates: [],
    };
  }

  const refreshedToken = await refreshBffAccessToken(token);
  const accessToken = extractAccessToken(refreshedToken);

  if (!accessToken) {
    throw new BffError("Unauthorized", 401);
  }

  return {
    accessToken,
    cookieUpdates: await refreshedJwtCookieUpdates(request, refreshedToken),
  };
}

export async function getAccessToken(request: Request): Promise<string> {
  return (await getAccessTokenResult(request)).accessToken;
}
