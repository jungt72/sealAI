// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { encode } from "next-auth/jwt";

import { getAccessTokenResult } from "./auth-token.ts";

const AUTH_SECRET = "test-auth-secret";
const KEYCLOAK_TOKEN_PATH = "/protocol/openid-connect/token";

async function expiredSessionRequest(refreshToken = "refresh-token"): Promise<Request> {
  const cookieName = "__Secure-authjs.session-token";
  const token = await encode({
    secret: AUTH_SECRET,
    salt: cookieName,
    token: {
      sub: "user-1",
      accessToken: "expired-access-token",
      refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) - 5,
    },
  });
  return new Request("https://sealingai.com/api/bff/workspace/case-1", {
    headers: { cookie: `${cookieName}=${token}`, "x-forwarded-proto": "https" },
  });
}

function keycloakRefreshResponse(overrides: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({
      access_token: "fresh-access-token",
      refresh_token: "rotated-refresh-token",
      expires_in: 300,
      ...overrides,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

let originalFetch: typeof globalThis.fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  process.env.AUTH_SECRET = AUTH_SECRET;
  process.env.KEYCLOAK_ISSUER = "https://keycloak.example/realms/sealAI";
  process.env.KEYCLOAK_CLIENT_ID = "nextauth";
  process.env.KEYCLOAK_CLIENT_SECRET = "client-secret";
  process.env.SEALAI_BACKEND_ORIGIN = "http://127.0.0.1:8000";
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete process.env.KEYCLOAK_ISSUER;
  delete process.env.KEYCLOAK_CLIENT_ID;
  delete process.env.KEYCLOAK_CLIENT_SECRET;
  delete process.env.SEALAI_BACKEND_ORIGIN;
});

describe("single-flight refresh", () => {
  it("collapses concurrent refreshes into exactly one Keycloak call", async () => {
    let keycloakCalls = 0;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      if (String(input).includes(KEYCLOAK_TOKEN_PATH)) {
        keycloakCalls += 1;
        // Delay so all four refreshes overlap while the first is in-flight.
        await new Promise((resolve) => setTimeout(resolve, 25));
        return keycloakRefreshResponse();
      }
      throw new Error(`unexpected fetch: ${String(input)}`);
    }) as typeof fetch;

    const request = await expiredSessionRequest();
    const results = await Promise.all([
      getAccessTokenResult(request),
      getAccessTokenResult(request),
      getAccessTokenResult(request),
      getAccessTokenResult(request),
    ]);

    expect(keycloakCalls).toBe(1);
    for (const result of results) {
      expect(result.accessToken).toBe("fresh-access-token");
    }
  });

  it("clears the in-flight slot on failure so the next attempt refreshes again", async () => {
    let keycloakCalls = 0;
    let mode: "fail" | "ok" = "fail";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      if (String(input).includes(KEYCLOAK_TOKEN_PATH)) {
        keycloakCalls += 1;
        if (mode === "fail") {
          return new Response(JSON.stringify({ error: "invalid_grant" }), { status: 400 });
        }
        return keycloakRefreshResponse();
      }
      throw new Error(`unexpected fetch: ${String(input)}`);
    }) as typeof fetch;

    const request = await expiredSessionRequest();
    await expect(getAccessTokenResult(request)).rejects.toMatchObject({ status: 401 });
    expect(keycloakCalls).toBe(1);

    mode = "ok";
    const result = await getAccessTokenResult(request);
    expect(keycloakCalls).toBe(2);
    expect(result.accessToken).toBe("fresh-access-token");
  });

  it("refreshes again on a subsequent cycle once the slot is freed", async () => {
    let keycloakCalls = 0;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      if (String(input).includes(KEYCLOAK_TOKEN_PATH)) {
        keycloakCalls += 1;
        return keycloakRefreshResponse({ access_token: `fresh-${keycloakCalls}` });
      }
      throw new Error(`unexpected fetch: ${String(input)}`);
    }) as typeof fetch;

    const request = await expiredSessionRequest();
    const first = await getAccessTokenResult(request);
    expect(keycloakCalls).toBe(1);
    const second = await getAccessTokenResult(request);
    expect(keycloakCalls).toBe(2);
    expect(first.accessToken).toBe("fresh-1");
    expect(second.accessToken).toBe("fresh-2");
  });
});
