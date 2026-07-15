import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearAccessToken,
  exchangeCode,
  getAccessToken,
  hasRefreshToken,
  msUntilExpiry,
  refreshTokens,
  type OidcConfig,
} from "./oidc";

const CFG: OidcConfig = {
  issuer: "https://sealingai.com/realms/sealAI",
  clientId: "sealai-v2",
  redirectUri: `${location.origin}/dashboard/callback`,
};

afterEach(() => {
  clearAccessToken();
  vi.unstubAllGlobals();
});

function ok(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function login(refresh = "rt-1"): Promise<void> {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      ok({ access_token: "at-1", expires_in: 1800, refresh_token: refresh, id_token: "id-1" }),
    ),
  );
  await exchangeCode(CFG, "code-xyz", "verifier");
}

function refreshTokenOf(mock: ReturnType<typeof vi.fn>): string | null {
  const init = mock.mock.calls[0][1] as RequestInit;
  return (init.body as URLSearchParams).get("refresh_token");
}

describe("refreshTokens (rotating silent refresh)", () => {
  it("captures the refresh token at login and ROTATES it on each refresh", async () => {
    await login("rt-1");
    expect(hasRefreshToken()).toBe(true);
    expect(getAccessToken()).toBe("at-1");

    const f1 = vi
      .fn()
      .mockResolvedValue(ok({ access_token: "at-2", expires_in: 1800, refresh_token: "rt-2" }));
    vi.stubGlobal("fetch", f1);
    await refreshTokens(CFG);
    expect(getAccessToken()).toBe("at-2"); // new access token stored
    const init = f1.mock.calls[0][1] as RequestInit;
    expect((init.body as URLSearchParams).get("grant_type")).toBe("refresh_token");
    expect(refreshTokenOf(f1)).toBe("rt-1"); // used the current token

    const f2 = vi
      .fn()
      .mockResolvedValue(ok({ access_token: "at-3", expires_in: 1800, refresh_token: "rt-3" }));
    vi.stubGlobal("fetch", f2);
    await refreshTokens(CFG);
    expect(refreshTokenOf(f2)).toBe("rt-2"); // ROTATION: the second refresh used the new token
  });

  it("coalesces concurrent refreshes into ONE request (rotation-safe single-flight)", async () => {
    await login("rt-1");
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => {
        calls += 1;
        return Promise.resolve(
          ok({ access_token: "at-2", expires_in: 1800, refresh_token: "rt-2" }),
        );
      }),
    );
    // three callers fire at once (timer + visibility + ...) → exactly one token request
    await Promise.all([refreshTokens(CFG), refreshTokens(CFG), refreshTokens(CFG)]);
    expect(calls).toBe(1);
    // after it settles, a fresh call issues a NEW request (the gate reset)
    await refreshTokens(CFG);
    expect(calls).toBe(2);
  });

  it("drops the refresh token + throws on a non-OK response (never retries a dead token)", async () => {
    await login("rt-1");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 400 })));
    await expect(refreshTokens(CFG)).rejects.toThrow();
    expect(hasRefreshToken()).toBe(false);
    await expect(refreshTokens(CFG)).rejects.toThrow(/no refresh token/);
  });

  it("replaces the complete credential set on a new authorization", async () => {
    await login("rt-old");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(ok({ access_token: "at-new", expires_in: 1800 })),
    );

    await exchangeCode(CFG, "new-code", "new-verifier");

    expect(getAccessToken()).toBe("at-new");
    expect(hasRefreshToken()).toBe(false);
  });

  it("never republishes tokens when logout clears a refresh already in flight", async () => {
    await login("rt-1");
    let resolveRefresh: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
          }),
      ),
    );

    const pending = refreshTokens(CFG);
    clearAccessToken();
    resolveRefresh?.(
      ok({ access_token: "late-access", expires_in: 1800, refresh_token: "late-refresh" }),
    );

    await expect(pending).rejects.toThrow(/superseded/);
    expect(getAccessToken()).toBeNull();
    expect(hasRefreshToken()).toBe(false);
  });

  it("never lets a late failed refresh erase a newly authenticated session", async () => {
    await login("rt-old");
    let resolveOldRefresh: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            resolveOldRefresh = resolve;
          }),
      ),
    );

    const oldPending = refreshTokens(CFG);
    clearAccessToken();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        ok({
          access_token: "at-new",
          expires_in: 1800,
          refresh_token: "rt-new",
        }),
      ),
    );
    await exchangeCode(CFG, "new-code", "new-verifier");

    resolveOldRefresh?.(new Response("old session revoked", { status: 400 }));
    await expect(oldPending).rejects.toThrow(/refresh failed/);
    expect(getAccessToken()).toBe("at-new");
    expect(hasRefreshToken()).toBe(true);

    const nextRefresh = vi
      .fn()
      .mockResolvedValue(
        ok({ access_token: "at-newer", expires_in: 1800, refresh_token: "rt-newer" }),
      );
    vi.stubGlobal("fetch", nextRefresh);
    await refreshTokens(CFG);
    expect(refreshTokenOf(nextRefresh)).toBe("rt-new");
  });

  it("exposes msUntilExpiry (positive right after login) for the scheduler", async () => {
    await login();
    expect(msUntilExpiry()).toBeGreaterThan(60_000);
  });
});
