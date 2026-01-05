import type { NextAuthOptions } from "next-auth";
import { randomUUID } from "crypto";
import KeycloakProvider from "next-auth/providers/keycloak";
import { deleteTokens, getTokens, putTokens } from "@/lib/auth-token-store";
import { isRefreshTokenExpired, isTokenExpired, refreshAccessToken } from "@/lib/keycloak-refresh";

const normalizeIssuer = (value: string): string => value.replace(/\/+$/, "");

const requireEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env: ${name}`);
  }
  return value;
};

const normalizeExpires = (value: string | number | null | undefined): number | null => {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const SESSION_MAX_AGE_SECONDS = 1800;
const SESSION_UPDATE_AGE_SECONDS = 300;
const DISCOVERY_TTL_MS = 10 * 60 * 1000;
let lastDiscoveryOkAt = 0;

const truncate = (value: string, max = 1200): string =>
  value.length > max ? `${value.slice(0, max)}…` : value;

const sanitizeError = (err: Error) => ({
  name: err.name,
  message: truncate(err.message),
  stack: err.stack ? truncate(err.stack) : undefined,
});

const sanitizeMetadata = (meta: unknown): Record<string, unknown> | undefined => {
  if (!meta) return undefined;
  if (meta instanceof Error) return sanitizeError(meta);
  if (typeof meta !== "object") {
    return { message: truncate(String(meta)) };
  }
  const record = meta as Record<string, unknown>;
  const output: Record<string, unknown> = {};
  if (typeof record.name === "string") output.name = truncate(record.name);
  if (typeof record.message === "string") output.message = truncate(record.message);
  if (typeof record.stack === "string") output.stack = truncate(record.stack);
  if (record.cause instanceof Error) output.cause = sanitizeError(record.cause);
  if (typeof record.cause === "string") output.cause = truncate(record.cause);
  if (typeof record.url === "string") output.url = truncate(record.url);
  if (typeof record.status === "number") output.status = record.status;
  return Object.keys(output).length ? output : undefined;
};

const sanitizeEventError = (error: unknown) => {
  if (!error) return undefined;
  if (error instanceof Error) return sanitizeError(error);
  return { message: truncate(String(error)) };
};

const safeBase = (value: string) => {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return value.split("?")[0];
  }
};

export const resolveRedirectUrl = (url: string, baseUrl: string): string => {
  let baseOrigin = "";
  let fallback = "/dashboard";
  try {
    baseOrigin = new URL(baseUrl).origin;
    fallback = `${baseOrigin}/dashboard`;
  } catch {
    return fallback;
  }

  if (url.startsWith("/")) return `${baseOrigin}${url}`;

  try {
    const target = new URL(url);
    if (target.hostname === "localhost" || target.hostname === "127.0.0.1" || target.hostname === "::1") {
      return fallback;
    }
    if (target.origin !== baseOrigin) return fallback;
    return `${baseOrigin}${target.pathname}${target.search}${target.hash}`;
  } catch {
    return fallback;
  }
};

export const getAuthOptions = async (): Promise<NextAuthOptions> => {
  const issuer = normalizeIssuer(requireEnv("KEYCLOAK_ISSUER"));
  const clientId = requireEnv("KEYCLOAK_CLIENT_ID");
  requireEnv("NEXTAUTH_SECRET");

  const rawClientSecret = process.env.KEYCLOAK_CLIENT_SECRET;
  const explicitClientType = process.env.KEYCLOAK_CLIENT_TYPE;
  const clientType =
    explicitClientType === "public" || explicitClientType === "confidential"
      ? explicitClientType
      : rawClientSecret
        ? "confidential"
        : "public";

  if (clientType === "confidential" && !rawClientSecret) {
    throw new Error("Missing KEYCLOAK_CLIENT_SECRET for confidential client.");
  }

  console.info(
    `[auth] keycloak config issuer=${issuer} clientId=${clientId} clientSecretPresent=${Boolean(rawClientSecret)}`,
  );

  const discoveryUrl = `${issuer}/.well-known/openid-configuration`;
  const now = Date.now();
  if (!lastDiscoveryOkAt || now - lastDiscoveryOkAt > DISCOVERY_TTL_MS) {
    try {
      const discoveryRes = await fetch(discoveryUrl, { cache: "no-store" });
      if (!discoveryRes.ok) {
        throw new Error(`Keycloak discovery failed (${discoveryRes.status})`);
      }
      lastDiscoveryOkAt = now;
    } catch (error) {
      console.error(`[auth] keycloak discovery failed url=${discoveryUrl}`, error);
      throw error;
    }
  }

  return {
    debug: process.env.NEXTAUTH_DEBUG === "true",
    logger: {
      error(code, metadata) {
        const safe = sanitizeMetadata(metadata);
        if (safe) {
          console.error("[nextauth][error]", code, safe);
        } else {
          console.error("[nextauth][error]", code);
        }
      },
      warn(code, metadata) {
        const safe = sanitizeMetadata(metadata);
        if (safe) {
          console.warn("[nextauth][warn]", code, safe);
        } else {
          console.warn("[nextauth][warn]", code);
        }
      },
      debug(code, metadata) {
        const safe = sanitizeMetadata(metadata);
        if (safe) {
          console.debug("[nextauth][debug]", code, safe);
        } else {
          console.debug("[nextauth][debug]", code);
        }
      },
    },
    // Keep session/jwt lifetimes explicit to avoid ghost sessions when SSO expires.
    session: { strategy: "jwt", maxAge: SESSION_MAX_AGE_SECONDS, updateAge: SESSION_UPDATE_AGE_SECONDS },
    jwt: { maxAge: SESSION_MAX_AGE_SECONDS },

    providers: [
      KeycloakProvider({
        issuer,
        clientId,
        clientSecret: clientType === "confidential" ? rawClientSecret : undefined,
        checks: ["pkce", "state"],
        client: { token_endpoint_auth_method: "client_secret_post" },
        authorization: { params: { scope: "openid profile email offline_access" } },
      }),
    ],

    callbacks: {
      async signIn({ account }) {
        const provider = account?.provider ?? "unknown";
        console.info("[nextauth][signIn]", { provider });
        return true;
      },
      // persist tokens server-side on initial login to keep JWT small
      async jwt({ token, account }) {
        if (account) {
          const expiresAt = normalizeExpires((account as any).expires_at ?? null);
          const refreshExpiresIn = normalizeExpires(
            (account as any).refresh_expires_in ?? (account as any).refresh_token_expires_in ?? null,
          );
          const now = Math.floor(Date.now() / 1000);
          const refreshExpiresAt =
            typeof refreshExpiresIn === "number" && refreshExpiresIn > 0
              ? now + refreshExpiresIn
              : now + SESSION_MAX_AGE_SECONDS;
          const jti =
            typeof (token as any).jti === "string" && (token as any).jti.length > 0
              ? (token as any).jti
              : randomUUID();
          (token as any).jti = jti;
          await putTokens(
            jti,
            {
              accessToken: (account as any).access_token ?? null,
              refreshToken: (account as any).refresh_token ?? null,
              idToken: (account as any).id_token ?? null,
              expires_at: expiresAt,
              refreshTokenExpires: refreshExpiresAt,
            },
            SESSION_MAX_AGE_SECONDS,
          );
          (token as any).accessToken = (account as any).access_token ?? null;
          (token as any).expires_at = expiresAt ?? null;
          (token as any).error = null;
          return token;
        }

        if ((token as any).error === "RefreshAccessTokenError") {
          return token;
        }

        const jti = typeof (token as any).jti === "string" ? (token as any).jti : null;
        if (!jti) return token;

        const stored = await getTokens(jti);
        if (!stored) {
          if (typeof (token as any).accessToken === "string" && (token as any).accessToken.length > 0) {
            return token;
          }
          return {
            ...token,
            error: "RefreshTokenMissing",
          } as typeof token;
        }
        (token as any).accessToken = stored.accessToken ?? null;

        const refreshExpiresAt = normalizeExpires(stored.refreshTokenExpires ?? null);
        const accessExpiresAt = normalizeExpires(stored.expires_at ?? null);
        const refreshToken = stored.refreshToken ?? null;

        if (refreshToken && isRefreshTokenExpired(refreshExpiresAt)) {
          await deleteTokens(jti);
          return {
            ...token,
            error: "RefreshTokenExpired",
          } as typeof token;
        }

        if (isTokenExpired(accessExpiresAt) && !refreshToken) {
          console.warn("Keycloak refresh token missing while access token expired.");
          return {
            ...token,
            error: "RefreshTokenMissing",
          } as typeof token;
        }

        if (isTokenExpired(accessExpiresAt) && refreshToken) {
          return refreshAccessToken(token as any);
        }

        return token;
      },

      // macht Tokens in der Client-Session verfügbar
      async session({ session, token }) {
        (session as any).error = (token as any).error ?? null;
        return session;
      },

      async redirect({ url, baseUrl }) {
        console.info("[nextauth][redirect][input]", {
          url: safeBase(url),
          baseUrl: safeBase(baseUrl),
        });
        const resolved = resolveRedirectUrl(url, baseUrl);
        console.info("[nextauth][redirect][resolved]", {
          resolved: safeBase(resolved),
          sanitized: resolved !== url && !url.startsWith("/"),
        });
        return resolved;
      },
    },

    events: {
      error(error) {
        const safe = sanitizeEventError(error);
        if (safe) {
          console.error("[nextauth][event][error]", safe);
        } else {
          console.error("[nextauth][event][error]");
        }
      },
    },

    pages: {
      signIn: "/auth/signin",
    },
  };
};
