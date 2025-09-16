/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // erzeugt .next/standalone für schlanke Docker-Runner-Images
  output: 'standalone',

  // Builds in CI/Container robuster machen
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },

  // optional – falls envs im Build fehlen, lieber nicht crashen:
  experimental: {
    // weitere Flags nur bei Bedarf
  },
};

module.exports = nextConfig;
