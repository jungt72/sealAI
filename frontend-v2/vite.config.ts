import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Served by nginx under /dashboard (static; client-side routed). The V2 client talks ONLY to
// /api/v2 (+ Keycloak) — never the V1 backend.
export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  server: { port: 5174 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
  },
});
