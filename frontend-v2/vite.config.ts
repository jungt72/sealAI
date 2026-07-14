import { existsSync, lstatSync, statSync } from "node:fs";
import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const candidateOutput = ".build/dashboard-candidate";

export function assertCandidateOutputSafe(
  root: string,
  configuredOutput: string,
): void {
  const expectedOutput = resolve(root, candidateOutput);
  const resolvedOutput = resolve(root, configuredOutput);
  const liveOutput = resolve(root, "dist");
  if (resolvedOutput !== expectedOutput) {
    throw new Error(
      "Refusing a non-candidate build output; use the gated dashboard publisher.",
    );
  }

  // Reject an existing symlink at any candidate path component. A lexical
  // outDir check alone would allow `.build` or the candidate directory to
  // redirect normal build writes into the live `dist` bind mount.
  let current = root;
  for (const component of [".build", "dashboard-candidate"]) {
    current = resolve(current, component);
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) {
      throw new Error("Refusing a symlinked dashboard candidate output.");
    }
  }
  if (existsSync(expectedOutput) && existsSync(liveOutput)) {
    const candidate = statSync(expectedOutput);
    const live = statSync(liveOutput);
    if (candidate.dev === live.dev && candidate.ino === live.ino) {
      throw new Error("Refusing a dashboard candidate alias to the live output.");
    }
  }
}

// Served by nginx under /dashboard (static; client-side routed). The V2 client talks ONLY to
// /api/v2 (+ Keycloak) — never the V1 backend.
export default defineConfig({
  base: "/dashboard/",
  build: {
    assetsInlineLimit: 0,
    // A normal build must never overwrite the host directory bind-mounted by
    // production nginx. Publishing remains a separately gated operation.
    outDir: candidateOutput,
  },
  plugins: [
    react(),
    (() => {
      let root = "";
      let configuredOutput = "";
      return {
        name: "sealai-deny-live-dashboard-build",
        apply: "build",
        configResolved(config) {
          root = config.root;
          configuredOutput = config.build.outDir;
          assertCandidateOutputSafe(root, configuredOutput);
        },
        buildStart() {
          assertCandidateOutputSafe(root, configuredOutput);
        },
      };
    })(),
  ],
  server: { port: 5174 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
  },
});
