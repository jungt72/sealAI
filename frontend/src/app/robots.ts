import type { MetadataRoute } from "next";

import { getSiteUrl } from "@/lib/site";

/**
 * NOTE: this route is currently shadowed. `next-sitemap` (generateRobotsTxt:
 * true, see next-sitemap.config.js) writes a static `public/robots.txt` at
 * build time, and Next.js serves a static /public file ahead of a matching
 * app-router route — so this function never actually runs in production
 * today. Kept in sync with next-sitemap.config.js's `robotsTxtOptions`
 * anyway: if the postbuild step is ever removed, this becomes the real
 * source of truth again, and a stale one would fail silently.
 */
export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();

  return {
    rules: [
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
      // AI crawlers — see next-sitemap.config.js for the full rationale.
      { userAgent: "GPTBot", disallow: "/" },
      { userAgent: "ClaudeBot", disallow: "/" },
      { userAgent: "Google-Extended", disallow: "/" },
      { userAgent: "Applebot-Extended", disallow: "/" },
      { userAgent: "Bytespider", disallow: "/" },
      { userAgent: "CCBot", disallow: "/" },
      { userAgent: "meta-externalagent", disallow: "/" },
      { userAgent: "OAI-SearchBot", allow: "/" },
      { userAgent: "ChatGPT-User", allow: "/" },
      { userAgent: "Claude-SearchBot", allow: "/" },
      { userAgent: "Claude-User", allow: "/" },
      { userAgent: "PerplexityBot", allow: "/" },
    ],
    sitemap: [`${siteUrl}/sitemap.xml`],
    host: siteUrl,
  };
}
