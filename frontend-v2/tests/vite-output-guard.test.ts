import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { assertCandidateOutputSafe } from "../vite.config";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function buildRoot(): string {
  const root = mkdtempSync(join(tmpdir(), "sealai-vite-output-"));
  roots.push(root);
  return root;
}

describe("dashboard candidate output guard", () => {
  it("accepts only the fixed candidate path", () => {
    const root = buildRoot();

    expect(() =>
      assertCandidateOutputSafe(root, ".build/dashboard-candidate"),
    ).not.toThrow();
    expect(() => assertCandidateOutputSafe(root, "dist")).toThrow(
      "Refusing a non-candidate build output",
    );
  });

  it("rejects a candidate directory symlinked to the live output", () => {
    const root = buildRoot();
    mkdirSync(join(root, ".build"));
    mkdirSync(join(root, "dist"));
    symlinkSync(join(root, "dist"), join(root, ".build", "dashboard-candidate"));

    expect(() =>
      assertCandidateOutputSafe(root, ".build/dashboard-candidate"),
    ).toThrow("Refusing a symlinked dashboard candidate output");
  });

  it("rejects a symlinked candidate ancestor", () => {
    const root = buildRoot();
    mkdirSync(join(root, "outside"));
    symlinkSync(join(root, "outside"), join(root, ".build"));

    expect(() =>
      assertCandidateOutputSafe(root, ".build/dashboard-candidate"),
    ).toThrow("Refusing a symlinked dashboard candidate output");
  });
});
