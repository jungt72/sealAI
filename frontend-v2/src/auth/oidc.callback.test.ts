import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeJwt } from "../../tests/jwt";
import {
  beginAuthorization,
  clearAccessToken,
  completeAuthorizationCallback,
  getAccessToken,
  scrubAuthorizationCallback,
  type OidcConfig,
} from "./oidc";

const CFG: OidcConfig = {
  issuer: "https://sealingai.com/realms/sealAI",
  clientId: "sealai-v2",
  redirectUri: `${location.origin}/dashboard/callback`,
};
const NOW_MS = 2_000_000_000_000;
const NOW_S = Math.floor(NOW_MS / 1000);

afterEach(() => {
  clearAccessToken();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/dashboard/");
  vi.unstubAllGlobals();
});

function okToken(nonce: string, claims: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({
      access_token: "TEST",
      expires_in: 300,
      id_token: fakeJwt({
        iss: CFG.issuer,
        aud: CFG.clientId,
        nonce,
        iat: NOW_S,
        exp: NOW_S + 300,
        ...claims,
      }),
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

async function transaction(): Promise<{ callback: URL; nonce: string }> {
  const authorize = new URL(await beginAuthorization(CFG, { now: NOW_MS }));
  const state = authorize.searchParams.get("state") as string;
  const nonce = authorize.searchParams.get("nonce") as string;
  return {
    callback: new URL(`${CFG.redirectUri}?code=one-time-code&state=${encodeURIComponent(state)}`),
    nonce,
  };
}

describe("OIDC one-time callback correlation", () => {
  it("binds state + PKCE + nonce and publishes tokens only after iss/aud validation", async () => {
    const { callback, nonce } = await transaction();
    const fetchFn = vi.fn().mockResolvedValue(okToken(nonce));
    vi.stubGlobal("fetch", fetchFn);

    await completeAuthorizationCallback(CFG, callback, NOW_MS);

    expect(getAccessToken()).toBe("TEST");
    expect(fetchFn).toHaveBeenCalledTimes(1);
    const request = fetchFn.mock.calls[0][1] as RequestInit;
    expect((request.body as URLSearchParams).get("code_verifier")).toMatch(
      /^[A-Za-z0-9_-]{43,128}$/,
    );
  });

  it("denies missing, mismatched and replayed state before another token request", async () => {
    const { callback, nonce } = await transaction();
    callback.searchParams.set("state", "mismatch");
    const fetchFn = vi.fn().mockResolvedValue(okToken(nonce));
    vi.stubGlobal("fetch", fetchFn);
    await expect(completeAuthorizationCallback(CFG, callback, NOW_MS)).rejects.toThrow(
      "callback rejected",
    );
    expect(fetchFn).not.toHaveBeenCalled();

    // The failed attempt consumed the transaction. Correcting state cannot replay it.
    const fresh = await transaction();
    fetchFn.mockResolvedValue(okToken(fresh.nonce));
    await completeAuthorizationCallback(CFG, fresh.callback, NOW_MS);
    await expect(completeAuthorizationCallback(CFG, fresh.callback, NOW_MS)).rejects.toThrow(
      "callback rejected",
    );
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["nonce", { nonce: "wrong" }],
    ["issuer", { iss: "https://evil.example/realms/x" }],
    ["audience", { aud: "another-client" }],
  ])("denies a mismatched %s without publishing the access token", async (_name, claims) => {
    const { callback, nonce } = await transaction();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okToken(nonce, claims)));
    await expect(completeAuthorizationCallback(CFG, callback, NOW_MS)).rejects.toThrow(
      "response rejected",
    );
    expect(getAccessToken()).toBeNull();
  });

  it("denies an expired transaction without a token request", async () => {
    const { callback } = await transaction();
    const fetchFn = vi.fn();
    vi.stubGlobal("fetch", fetchFn);
    await expect(
      completeAuthorizationCallback(CFG, callback, NOW_MS + 5 * 60_000 + 1),
    ).rejects.toThrow("callback rejected");
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("denies duplicate state/code and a mismatched authorization response issuer", async () => {
    for (const mutate of [
      (url: URL) => url.searchParams.append("state", "duplicate"),
      (url: URL) => url.searchParams.append("code", "duplicate"),
      (url: URL) => url.searchParams.set("iss", "https://evil.example/realms/x"),
    ]) {
      const { callback } = await transaction();
      mutate(callback);
      const fetchFn = vi.fn();
      vi.stubGlobal("fetch", fetchFn);
      await expect(completeAuthorizationCallback(CFG, callback, NOW_MS)).rejects.toThrow(
        "callback rejected",
      );
      expect(fetchFn).not.toHaveBeenCalled();
    }
  });

  it("scrubs code/state/error from history synchronously", () => {
    window.history.replaceState({}, "", "/dashboard/callback?code=secret&state=secret");
    scrubAuthorizationCallback();
    expect(window.location.pathname).toBe("/dashboard/");
    expect(window.location.search).toBe("");
  });
});
