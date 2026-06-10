import { afterEach, describe, expect, it } from "vitest";

import {
  challengeFromVerifier,
  clearAccessToken,
  getAccessToken,
  randomVerifier,
  setAccessToken,
} from "./oidc";

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
