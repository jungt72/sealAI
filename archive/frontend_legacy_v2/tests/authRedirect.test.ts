import { describe, expect, it } from "vitest";

import { resolveRedirectUrl } from "../src/lib/auth-options";

describe("resolveRedirectUrl", () => {
  it("returns baseUrl + path for relative URLs", () => {
    expect(resolveRedirectUrl("/chat", "https://sealai.net")).toBe("https://sealai.net/chat");
  });

  it("sanitizes localhost callback URLs to baseUrl origin", () => {
    expect(resolveRedirectUrl("http://localhost:3000/chat", "https://sealai.net")).toBe(
      "https://sealai.net/dashboard",
    );
  });

  it("sanitizes 127.0.0.1 callback URLs to baseUrl origin", () => {
    expect(resolveRedirectUrl("http://127.0.0.1:3000/chat", "https://sealai.net")).toBe(
      "https://sealai.net/dashboard",
    );
  });

  it("sanitizes ::1 callback URLs to baseUrl origin", () => {
    expect(resolveRedirectUrl("http://[::1]:3000/chat", "https://sealai.net")).toBe(
      "https://sealai.net/dashboard",
    );
  });

  it("keeps same-origin absolute URLs but normalizes origin", () => {
    expect(resolveRedirectUrl("https://sealai.net/dashboard?x=1#h", "https://sealai.net")).toBe(
      "https://sealai.net/dashboard?x=1#h",
    );
  });

  it("falls back for foreign origins", () => {
    expect(resolveRedirectUrl("https://evil.com/chat", "https://sealai.net")).toBe(
      "https://sealai.net/dashboard",
    );
  });

  it("falls back to /dashboard when baseUrl is invalid", () => {
    expect(resolveRedirectUrl("https://sealai.net/chat", "not-a-url")).toBe("/dashboard");
  });
});
