import test from "node:test";
import assert from "node:assert/strict";

import { canonicalizeAppUrl, isProtectedPath, shouldRedirectToSignIn } from "./proxy-auth.ts";

test("canonicalizeAppUrl redirects legacy and www hosts to sealingai.com", () => {
  assert.equal(
    canonicalizeAppUrl(new URL("http://sealai.net/dashboard/new?x=1"))?.toString(),
    "https://sealingai.com/dashboard/new?x=1",
  );
  assert.equal(
    canonicalizeAppUrl(new URL("https://www.sealingai.com/wissen"))?.toString(),
    "https://sealingai.com/wissen",
  );
});

test("canonicalizeAppUrl leaves the canonical host and local development alone", () => {
  assert.equal(canonicalizeAppUrl(new URL("https://sealingai.com/dashboard")), null);
  assert.equal(canonicalizeAppUrl(new URL("http://127.0.0.1:3000/dashboard")), null);
});

test("isProtectedPath matches dashboard routes", () => {
  assert.equal(isProtectedPath("/dashboard"), true);
  assert.equal(isProtectedPath("/dashboard/cases/123"), true);
});

test("isProtectedPath matches rag routes", () => {
  assert.equal(isProtectedPath("/rag"), true);
  assert.equal(isProtectedPath("/rag/documents"), true);
});

test("isProtectedPath matches goal routes", () => {
  assert.equal(isProtectedPath("/goal"), true);
  assert.equal(isProtectedPath("/goal/new"), true);
});

test("isProtectedPath ignores unprotected routes", () => {
  assert.equal(isProtectedPath("/"), false);
  assert.equal(isProtectedPath("/api/auth/signin"), false);
  assert.equal(isProtectedPath("/login"), false);
  assert.equal(isProtectedPath("/settings"), false);
});

test("shouldRedirectToSignIn only redirects unauthenticated protected requests", () => {
  assert.equal(shouldRedirectToSignIn("/dashboard", false), true);
  assert.equal(shouldRedirectToSignIn("/rag", false), true);
  assert.equal(shouldRedirectToSignIn("/goal", false), true);
  assert.equal(shouldRedirectToSignIn("/dashboard", true), false);
  assert.equal(shouldRedirectToSignIn("/", false), false);
});
