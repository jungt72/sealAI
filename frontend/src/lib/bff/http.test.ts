import assert from "node:assert/strict";
import test from "node:test";

import { encode } from "next-auth/jwt";

import { buildBackendUrl } from "./backend.ts";
import { BffError } from "./errors.ts";
import { getAccessToken, getAccessTokenResult } from "./auth-token.ts";

const AUTH_SECRET = "test-auth-secret";

async function buildSessionCookie({
  secureCookie,
  accessToken,
  refreshToken,
  expiresAt,
  legacyCookieName = false,
}: {
  secureCookie: boolean;
  accessToken: string;
  refreshToken?: string;
  expiresAt?: number;
  legacyCookieName?: boolean;
}): Promise<string> {
  const baseName = legacyCookieName ? "next-auth.session-token" : "authjs.session-token";
  const cookieName = secureCookie ? `__Secure-${baseName}` : baseName;
  const token = await encode({
    secret: AUTH_SECRET,
    salt: cookieName,
    token: {
      sub: "user-1",
      accessToken,
      ...(refreshToken ? { refreshToken } : {}),
      ...(typeof expiresAt === "number" ? { expiresAt } : {}),
    },
  });

  return `${cookieName}=${token}`;
}

test("getAccessToken reads the secure Auth.js session cookie from the request", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const cookie = await buildSessionCookie({
    secureCookie: true,
    accessToken: "access-token-from-cookie",
    expiresAt: Math.floor(Date.now() / 1000) + 300,
  });
  const request = new Request("https://sealingai.com/api/bff/agent/chat/stream", {
    headers: {
      cookie,
      "x-forwarded-proto": "https",
    },
  });

  const accessToken = await getAccessToken(request);

  assert.equal(accessToken, "access-token-from-cookie");
});

test("getAccessToken detects secure Auth.js cookies even when proxy proto is absent", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const cookie = await buildSessionCookie({
    secureCookie: true,
    accessToken: "access-token-from-secure-cookie",
    expiresAt: Math.floor(Date.now() / 1000) + 300,
  });
  const request = new Request("http://sealingai.com/api/bff/agent/cases", {
    headers: { cookie },
  });

  const accessToken = await getAccessToken(request);

  assert.equal(accessToken, "access-token-from-secure-cookie");
});

test("getAccessToken accepts legacy secure NextAuth session cookies during migration", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const cookie = await buildSessionCookie({
    secureCookie: true,
    legacyCookieName: true,
    accessToken: "access-token-from-legacy-cookie",
    expiresAt: Math.floor(Date.now() / 1000) + 300,
  });
  const request = new Request("https://sealingai.com/api/bff/agent/cases", {
    headers: { cookie },
  });

  const accessToken = await getAccessToken(request);

  assert.equal(accessToken, "access-token-from-legacy-cookie");
});

test("getAccessToken refreshes expired Keycloak access tokens for BFF calls", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  process.env.KEYCLOAK_ISSUER = "https://keycloak.example/realms/sealAI";
  process.env.KEYCLOAK_CLIENT_ID = "nextauth";
  process.env.KEYCLOAK_CLIENT_SECRET = "client-secret";
  const cookie = await buildSessionCookie({
    secureCookie: true,
    accessToken: "expired-access-token",
    refreshToken: "refresh-token",
    expiresAt: Math.floor(Date.now() / 1000) - 5,
  });
  const request = new Request("https://sealingai.com/api/bff/agent/chat/stream", {
    headers: {
      cookie,
      "x-forwarded-proto": "https",
    },
  });
  const originalFetch = globalThis.fetch;
  let refreshBody = "";
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    refreshBody = String(init?.body || "");
    return new Response(
      JSON.stringify({
        access_token: "fresh-access-token",
        refresh_token: "rotated-refresh-token",
        expires_in: 300,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    const accessToken = await getAccessToken(request);

    assert.equal(accessToken, "fresh-access-token");
    assert.match(refreshBody, /grant_type=refresh_token/);
    assert.match(refreshBody, /refresh_token=refresh-token/);
  } finally {
    globalThis.fetch = originalFetch;
    delete process.env.KEYCLOAK_ISSUER;
    delete process.env.KEYCLOAK_CLIENT_ID;
    delete process.env.KEYCLOAK_CLIENT_SECRET;
  }
});

test("getAccessTokenResult returns rotated Auth.js session cookie updates", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  process.env.KEYCLOAK_ISSUER = "https://keycloak.example/realms/sealAI";
  process.env.KEYCLOAK_CLIENT_ID = "nextauth";
  process.env.KEYCLOAK_CLIENT_SECRET = "client-secret";
  const cookie = await buildSessionCookie({
    secureCookie: true,
    accessToken: "expired-access-token",
    refreshToken: "refresh-token",
    expiresAt: Math.floor(Date.now() / 1000) - 5,
  });
  const request = new Request("https://sealingai.com/api/bff/agent/chat/stream", {
    headers: {
      cookie,
      "x-forwarded-proto": "https",
    },
  });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        access_token: "fresh-access-token",
        refresh_token: "rotated-refresh-token",
        expires_in: 300,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    )) as typeof fetch;

  try {
    const result = await getAccessTokenResult(request);

    assert.equal(result.accessToken, "fresh-access-token");
    assert.ok(result.cookieUpdates.length >= 1);
    assert.ok(
      result.cookieUpdates.some((update) =>
        update.name === "__Secure-authjs.session-token" ||
        update.name.startsWith("__Secure-authjs.session-token."),
      ),
    );
    assert.ok(result.cookieUpdates.every((update) => update.options.httpOnly));
    assert.ok(result.cookieUpdates.every((update) => update.options.secure));
  } finally {
    globalThis.fetch = originalFetch;
    delete process.env.KEYCLOAK_ISSUER;
    delete process.env.KEYCLOAK_CLIENT_ID;
    delete process.env.KEYCLOAK_CLIENT_SECRET;
  }
});

test("getAccessToken rejects requests without a session cookie", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const request = new Request("https://sealingai.com/api/bff/workspace/case-1");

  await assert.rejects(
    () => getAccessToken(request),
    (error: unknown) =>
      error instanceof BffError &&
      error.status === 401 &&
      error.message === "Unauthorized",
  );
});

test("buildBackendUrl prefers the internal backend origin over the public site URL", () => {
  const previousBackendOrigin = process.env.SEALAI_BACKEND_ORIGIN;
  const previousPublicBase = process.env.NEXT_PUBLIC_API_BASE;

  process.env.SEALAI_BACKEND_ORIGIN = "http://127.0.0.1:8000/";
  process.env.NEXT_PUBLIC_API_BASE = "https://sealingai.com";

  try {
    assert.equal(
      buildBackendUrl("/api/agent/chat/stream"),
      "http://127.0.0.1:8000/api/agent/chat/stream",
    );
  } finally {
    if (previousBackendOrigin === undefined) {
      delete process.env.SEALAI_BACKEND_ORIGIN;
    } else {
      process.env.SEALAI_BACKEND_ORIGIN = previousBackendOrigin;
    }

    if (previousPublicBase === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE;
    } else {
      process.env.NEXT_PUBLIC_API_BASE = previousPublicBase;
    }
  }
});
