import test from "node:test";
import assert from "node:assert/strict";

import { isProtectedPath, shouldRedirectToSignIn } from "./proxy-auth.ts";

test("isProtectedPath matches dashboard routes", () => {
  assert.equal(isProtectedPath("/dashboard"), true);
  assert.equal(isProtectedPath("/dashboard/cases/123"), true);
});

test("isProtectedPath matches rag routes", () => {
  assert.equal(isProtectedPath("/rag"), true);
  assert.equal(isProtectedPath("/rag/documents"), true);
});

test("isProtectedPath ignores unprotected routes", () => {
  assert.equal(isProtectedPath("/"), false);
  assert.equal(isProtectedPath("/api/auth/signin"), false);
  assert.equal(isProtectedPath("/settings"), false);
});

test("shouldRedirectToSignIn only redirects unauthenticated protected requests", () => {
  assert.equal(shouldRedirectToSignIn("/dashboard", false), true);
  assert.equal(shouldRedirectToSignIn("/rag", false), true);
  assert.equal(shouldRedirectToSignIn("/dashboard", true), false);
  assert.equal(shouldRedirectToSignIn("/", false), false);
});
