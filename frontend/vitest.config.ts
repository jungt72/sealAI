/**
 * Vitest Konfiguration — jsdom-Umgebung für React-Komponenten-Tests.
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    // Nur Vitest-native Tests — node:test-Dateien laufen via test:node
    include: ["src/test/**/*.test.ts", "src/**/*.test.tsx", "src/**/*.spec.ts"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    passWithNoTests: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
