import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeJwt } from "../../tests/jwt";
import {
  challengeFromVerifier,
  clearAccessToken,
  getAccessToken,
  givenNameFromToken,
  logoutUrl,
  randomVerifier,
  rpInitiatedLogout,
  setAccessToken,
  type OidcConfig,
} from "./oidc";

const CFG: OidcConfig = {
  issuer: "https://sealingai.com/realms/sealAI",
  clientId: "sealai-v2",
  redirectUri: `${location.origin}/dashboard/callback`,
  postLogoutRedirectUri: `${location.origin}/dashboard/`,
};

afterEach(() => {
  clearAccessToken();
  localStorage.clear();
  sessionStorage.clear();
});

describe("oidc token store (check 4: in-memory only)", () => {
  it("holds the access token in memory and NEVER writes it to web storage", () => {
    setAccessToken("secret-access-token", 3600);
    expect(getAccessToken()).toBe("secret-access-token");
    // the token must not be findable in localStorage or sessionStorage
    const dump = JSON.stringify({ ...localStorage, ...sessionStorage });
    expect(dump).not.toContain("secret-access-token");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("treats an (near-)expired token as absent (fail-closed)", () => {
    setAccessToken("t", 10); // < 30s skew buffer → stale
    expect(getAccessToken()).toBeNull();
  });

  it("clears on demand", () => {
    setAccessToken("t", 3600);
    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });
});

describe("RP-initiated logout (Part 3: Abmelden must end the Keycloak SSO session)", () => {
  it("builds the realm's end-session URL without an authentication identifier", () => {
    const url = new URL(logoutUrl(CFG));
    expect(url.origin + url.pathname).toBe(
      "https://sealingai.com/realms/sealAI/protocol/openid-connect/logout",
    );
    expect(url.searchParams.has("id_token_hint")).toBe(false);
    expect(url.searchParams.get("post_logout_redirect_uri")).toBe(`${location.origin}/dashboard/`);
    expect(url.searchParams.get("client_id")).toBe("sealai-v2");
  });

  it("always omits id_token_hint (Keycloak may ask for confirmation)", () => {
    const url = new URL(logoutUrl(CFG));
    expect(url.searchParams.has("id_token_hint")).toBe(false);
    expect(url.searchParams.get("client_id")).toBe("sealai-v2"); // still identifies the client
    expect(url.searchParams.get("post_logout_redirect_uri")).toBe(`${location.origin}/dashboard/`);
  });

  it("falls back to the app origin when no postLogoutRedirectUri is configured", () => {
    const cfg = { ...CFG, postLogoutRedirectUri: undefined };
    const url = new URL(logoutUrl(cfg));
    expect(url.searchParams.get("post_logout_redirect_uri")).toBe(`${location.origin}/dashboard/`);
  });

  it("rpInitiatedLogout clears the local tokens BEFORE navigating to the end-session URL", () => {
    setAccessToken("acc-tok", 3600);
    let urlAtNavigate: string | null = null;
    let accessAtNavigate: string | null = "sentinel";
    rpInitiatedLogout(CFG, (url) => {
      urlAtNavigate = url;
      accessAtNavigate = getAccessToken(); // captured AT navigation time → proves ordering
    });
    expect(accessAtNavigate).toBeNull();
    const url = new URL(urlAtNavigate as unknown as string);
    expect(url.pathname).toBe("/realms/sealAI/protocol/openid-connect/logout");
    expect(url.searchParams.has("id_token_hint")).toBe(false);
  });
});

describe("givenNameFromToken (Part 2: greeting from the existing session's claim)", () => {
  it("returns the given_name claim from a token", () => {
    expect(givenNameFromToken(fakeJwt({ given_name: "Thorsten", sub: "u1" }))).toBe("Thorsten");
  });

  it("decodes UTF-8 names correctly (umlauts)", () => {
    expect(givenNameFromToken(fakeJwt({ given_name: "Jürgen" }))).toBe("Jürgen");
  });

  it("falls back to null when the claim is absent", () => {
    expect(givenNameFromToken(fakeJwt({ sub: "u1", sid: "s1" }))).toBeNull();
  });

  it("falls back to null on blank or non-string given_name", () => {
    expect(givenNameFromToken(fakeJwt({ given_name: "   " }))).toBeNull();
    expect(givenNameFromToken(fakeJwt({ given_name: 42 }))).toBeNull();
  });

  it("falls back to null on missing or malformed tokens (never throws)", () => {
    expect(givenNameFromToken(null)).toBeNull();
    expect(givenNameFromToken("")).toBeNull();
    expect(givenNameFromToken("not-a-jwt")).toBeNull();
    expect(givenNameFromToken("a.%%%not-base64%%%.c")).toBeNull();
    expect(givenNameFromToken(`a.${btoa("not json")}.c`)).toBeNull();
  });

  it("never logs the token or the name (no PII in the console)", () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) =>
      vi.spyOn(console, m),
    );
    givenNameFromToken(fakeJwt({ given_name: "Thorsten" }));
    givenNameFromToken("not-a-jwt");
    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    }
  });
});

describe("PKCE", () => {
  it("generates a verifier and an S256 challenge (base64url, no padding)", async () => {
    const v = randomVerifier();
    expect(v).toMatch(/^[A-Za-z0-9_-]+$/);
    const c = await challengeFromVerifier(v);
    expect(c).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(c).not.toContain("=");
    expect(c).not.toBe(v); // challenge is the hash, not the verifier
  });
});
