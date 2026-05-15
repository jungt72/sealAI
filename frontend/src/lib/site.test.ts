import test from "node:test";
import assert from "node:assert/strict";

import { resolveSiteUrl } from "./site.ts";

test("resolveSiteUrl falls back to the default site URL", () => {
  assert.equal(resolveSiteUrl(undefined), "https://sealingai.com");
  assert.equal(resolveSiteUrl("   "), "https://sealingai.com");
});

test("resolveSiteUrl trims a trailing slash from configured URLs", () => {
  assert.equal(resolveSiteUrl("https://example.com/"), "https://example.com");
  assert.equal(resolveSiteUrl("https://example.com/app"), "https://example.com/app");
});
