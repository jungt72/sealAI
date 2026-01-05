import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { isTokenExpired, refreshAccessToken } from "../src/lib/keycloak-refresh";
import { deleteTokens, getTokens, updateTokens } from "../src/lib/auth-token-store";

vi.mock("../src/lib/auth-token-store", () => ({
  getTokens: vi.fn(),
  updateTokens: vi.fn(),
  deleteTokens: vi.fn(),
}));

describe("Keycloak refresh helpers", () => {
  beforeEach(() => {
    process.env.KEYCLOAK_ISSUER = "https://auth.example.com/realms/test";
    process.env.KEYCLOAK_CLIENT_ID = "example-client";
    process.env.KEYCLOAK_CLIENT_SECRET = "shhh-secret";
    vi.mocked(getTokens).mockResolvedValue({
      accessToken: "old-access",
      refreshToken: "refresh-token",
      idToken: "old-id",
      refreshTokenExpires: Math.floor(Date.now() / 1000) + 3600,
    });
    vi.mocked(updateTokens).mockResolvedValue(undefined);
    vi.mocked(deleteTokens).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("refreshes expired tokens", async () => {
    const now = 1_700_000_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);

    const successResponse = {
      ok: true,
      status: 200,
      statusText: "OK",
      json: () =>
        Promise.resolve({
          access_token: "new-access",
          refresh_token: "new-refresh",
          id_token: "new-id",
          expires_in: 600,
        }),
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(successResponse)));

    const refreshed = await refreshAccessToken({
      accessToken: "old-access",
      refreshToken: "refresh-token",
      idToken: "old-id",
      jti: "token-id",
      expires_at: Math.floor(now / 1000) - 10,
    });

    expect(refreshed.accessToken).toBe("new-access");
    expect(refreshed.refreshToken).toBe("new-refresh");
    expect(refreshed.idToken).toBe("new-id");
    expect(refreshed.error).toBeNull();
    expect(refreshed.expires_at).toBe(Math.floor(now / 1000) + 600);
  });

  it("flags an error when refresh fails", async () => {
    const now = 1_700_100_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);

    const failureResponse = {
      ok: false,
      status: 401,
      statusText: "Unauthorized",
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(failureResponse)));

    const refreshed = await refreshAccessToken({
      accessToken: "old-access",
      refreshToken: "refresh-token",
      idToken: "old-id",
      jti: "token-id",
      expires_at: Math.floor(now / 1000) - 30,
    });

    expect(refreshed.accessToken).toBeNull();
    expect(refreshed.expires_at).toBeNull();
    expect(refreshed.error).toBe("RefreshAccessTokenError");
  });

  it("invalidates tokens when refresh is skipped", async () => {
    const now = 1_700_400_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);
    process.env.KEYCLOAK_ISSUER = "";

    const refreshed = await refreshAccessToken({
      accessToken: "old-access",
      refreshToken: "refresh-token",
      idToken: "old-id",
      jti: "token-id",
      expires_at: Math.floor(now / 1000) - 30,
    });

    expect(refreshed.accessToken).toBeNull();
    expect(refreshed.expires_at).toBeNull();
    expect(refreshed.error).toBe("RefreshAccessTokenError");
  });
});

describe("isTokenExpired", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns true once the clock passes the threshold", () => {
    const now = 1_700_200_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);

    expect(isTokenExpired(Math.floor(now / 1000) - 10)).toBe(true);
  });

  it("returns false while the token is still valid", () => {
    const now = 1_700_300_000_000;
    vi.spyOn(Date, "now").mockReturnValue(now);

    expect(isTokenExpired(Math.floor(now / 1000) + 120)).toBe(false);
  });
});
