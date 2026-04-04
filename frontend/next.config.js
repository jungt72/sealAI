const path = require("path");
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),

  // React Compiler (Next.js 16: top-level, nicht mehr experimental)
  // Automatisches Memoizing — ersetzt manuelles memo()/useMemo()/useCallback()
  reactCompiler: true,

  // Partial Pre-Rendering (Next.js 16: ehemals experimental.ppr → cacheComponents).
  // BLOCKED: Dashboard-Routen lesen Session-Daten außerhalb von <Suspense>.
  // Enablen erst nach Suspense-Boundary-Refactoring der Auth-Provider-Kette.
  // cacheComponents: true,

  experimental: {
    turbopackFileSystemCacheForDev: true,
    turbopackFileSystemCacheForBuild: true,
  },


  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
};

module.exports = withBundleAnalyzer(nextConfig);
