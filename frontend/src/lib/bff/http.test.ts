import assert from "node:assert/strict";
import test from "node:test";

import { encode } from "next-auth/jwt";

import { BffError } from "./errors.ts";
import { getAccessToken } from "./auth-token.ts";

const AUTH_SECRET = "test-auth-secret";

async function buildSessionCookie({
  secureCookie,
  accessToken,
}: {
  secureCookie: boolean;
  accessToken: string;
}): Promise<string> {
  const cookieName = secureCookie
    ? "__Secure-authjs.session-token"
    : "authjs.session-token";
  const token = await encode({
    secret: AUTH_SECRET,
    salt: cookieName,
    token: {
      sub: "user-1",
      accessToken,
    },
  });

  return `${cookieName}=${token}`;
}

test("getAccessToken reads the secure Auth.js session cookie from the request", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const cookie = await buildSessionCookie({
    secureCookie: true,
    accessToken: "access-token-from-cookie",
  });
  const request = new Request("https://sealai.net/api/bff/agent/chat/stream", {
    headers: {
      cookie,
      "x-forwarded-proto": "https",
    },
  });

  const accessToken = await getAccessToken(request);

  assert.equal(accessToken, "access-token-from-cookie");
});

test("getAccessToken rejects requests without a session cookie", async () => {
  process.env.AUTH_SECRET = AUTH_SECRET;
  const request = new Request("https://sealai.net/api/bff/workspace/case-1");

  await assert.rejects(
    () => getAccessToken(request),
    (error: unknown) =>
      error instanceof BffError &&
      error.status === 401 &&
      error.message === "Unauthorized",
  );
});
