const DEFAULT_SITE_URL = "https://sealai.net";

function getSiteUrl() {
  const value = process.env.NEXT_PUBLIC_SITE_URL ?? process.env.SITE_URL;
  const trimmed = value?.trim();

  if (!trimmed) {
    return DEFAULT_SITE_URL;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

/** @type {import('next-sitemap').IConfig} */
module.exports = {
  siteUrl: getSiteUrl(),
  generateRobotsTxt: true,
  changefreq: "weekly",
  priority: 0.7,
  sitemapSize: 5000,
  exclude: [
    "/api/*",
    "/dashboard",
    "/dashboard/*",
    "/goal",
    "/goal/*",
    "/rag",
    "/rag/*",
    "/robots.txt",
  ],
  robotsTxtOptions: {
    policies: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/api/",
          "/dashboard",
          "/dashboard/",
          "/dashboard/seo",
          "/dashboard/seo/",
          "/goal",
          "/goal/",
          "/rag",
          "/rag/",
        ],
      },
    ],
  },
  transform: async (config, path) => ({
    loc: path,
    changefreq: path === "/" ? "daily" : config.changefreq,
    priority: 
      path === "/" ? 1.0 : 
      path === "/anfrage/dichtung-auslegen-lassen" ? 0.95 :
      path === "/wissen" || path === "/werkstoffe" || path === "/medien" ? 0.95 :
      path.startsWith("/medien/") || path.startsWith("/werkstoffe/") || path.startsWith("/wissen/") ? 0.9 :
      0.7,
    lastmod: new Date().toISOString(),
    alternateRefs: config.alternateRefs ?? [],
  }),
};
