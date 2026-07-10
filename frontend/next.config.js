const path = require("path");
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),

  // Marketing pages are static but content changes (copy, design, article
  // edits) should be visible immediately after a deploy — the framework
  // default (s-maxage=1y) otherwise lets browsers/proxies sit on a stale
  // page for a very long time. Scoped to everything except /api and /login
  // so auth/API responses keep their own cache behavior.
  async headers() {
    return [
      {
        source: "/((?!api|login).*)",
        headers: [
          { key: "Cache-Control", value: "public, max-age=0, must-revalidate" },
        ],
      },
    ];
  },

  async redirects() {
    return [
      {
        source: "/sealingpedia",
        destination: "/wissen",
        permanent: true,
      },
      {
        source: "/sealing-pedia",
        destination: "/wissen",
        permanent: true,
      },
      {
        source: "/pedia",
        destination: "/wissen",
        permanent: true,
      },
      {
        source: "/wiki",
        destination: "/wissen",
        permanent: true,
      },
      {
        source: "/blog",
        destination: "/wissen",
        permanent: true,
      },
    ];
  },

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


};

module.exports = withBundleAnalyzer(nextConfig);
