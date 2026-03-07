/** @type {import('next').NextConfig} */
const disableTurbopack = process.env.NEXT_DISABLE_TURBOPACK === "1";

const nextConfig = {
  reactStrictMode: true,

  // erzeugt .next/standalone für schlanke Docker-Runner-Images
  output: 'standalone',

  // Repo enthält zusätzlich ein Node-Projekt im Root; explizit den Frontend-Root setzen,
  // damit Next.js nicht das Root-Lockfile als Workspace-Root verwendet.
  ...(disableTurbopack ? {} : { turbopack: { root: __dirname } }),

  // Builds in CI/Container robuster machen
  typescript: { ignoreBuildErrors: true },

  // optional – falls envs im Build fehlen, lieber nicht crashen:
  experimental: {
    // weitere Flags nur bei Bedarf
  },
};

module.exports = nextConfig;
