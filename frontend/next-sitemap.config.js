const fs = require("fs");
const path = require("path");

const DEFAULT_SITE_URL = "https://sealingai.com";
const CONTENT_ROOT = path.join(__dirname, "content");

function getSiteUrl() {
  const value = process.env.NEXT_PUBLIC_SITE_URL ?? process.env.SITE_URL;
  const trimmed = value?.trim();

  if (!trimmed) {
    return DEFAULT_SITE_URL;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

/**
 * Real per-article lastmod, read straight from the same frontmatter
 * (`datePublished` / `dateModified`) that drives the on-page Article schema —
 * see src/lib/content/loader.ts. A sitemap `lastmod` that's just "now" on
 * every entry (the previous behavior) is a well-known signal Google
 * discounts entirely, since it can't distinguish real updates from a
 * routine redeploy. Pages with no tracked content date (marketing/legal
 * pages) get no `lastmod` at all rather than a fabricated one.
 */
function readContentDate(urlPath) {
  const match = urlPath.match(/^\/(wissen|werkstoffe|medien)\/([^/]+)\/?$/);
  if (!match) return undefined;

  const [, type, slug] = match;
  const filePath = path.join(CONTENT_ROOT, type, `${slug}.md`);

  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const lines = raw.split("\n");
    if (lines[0]?.trim() !== "---") return undefined;

    const frontmatter = {};
    for (let i = 1; i < lines.length && lines[i]?.trim() !== "---"; i++) {
      const colonIndex = lines[i].indexOf(":");
      if (colonIndex === -1) continue;
      const key = lines[i].slice(0, colonIndex).trim();
      const value = lines[i].slice(colonIndex + 1).trim().replace(/^["']|["']$/g, "");
      frontmatter[key] = value;
    }

    const date = frontmatter.dateModified || frontmatter.datePublished;
    return date ? new Date(date).toISOString() : undefined;
  } catch {
    return undefined;
  }
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
      // AI crawlers: separate model-training collection from live AI-search
      // retrieval/citation. Blocking the former does not reduce eligibility
      // for the latter — they are architecturally distinct crawlers per
      // vendor. Matches Cloudflare's own managed-robots.txt default split
      // (ClaudeBot/GPTBot/Google-Extended/meta-externalagent disallowed by
      // default) rather than a single blog's opinion. Revisit if sealingAI's
      // stance on third-party model training changes.
      { userAgent: "GPTBot", disallow: "/" },
      { userAgent: "ClaudeBot", disallow: "/" },
      { userAgent: "Google-Extended", disallow: "/" },
      { userAgent: "Applebot-Extended", disallow: "/" },
      { userAgent: "Bytespider", disallow: "/" },
      { userAgent: "CCBot", disallow: "/" },
      { userAgent: "meta-externalagent", disallow: "/" },
      // Live AI search / answer / user-fetch bots — kept open so sealingAI
      // content stays eligible for ChatGPT/Claude/Perplexity answer citations.
      { userAgent: "OAI-SearchBot", allow: "/" },
      { userAgent: "ChatGPT-User", allow: "/" },
      { userAgent: "Claude-SearchBot", allow: "/" },
      { userAgent: "Claude-User", allow: "/" },
      { userAgent: "PerplexityBot", allow: "/" },
    ],
  },
  transform: async (config, urlPath) => {
    const entry = {
      loc: urlPath,
      changefreq: urlPath === "/" ? "daily" : config.changefreq,
      priority:
        urlPath === "/" ? 1.0 :
        urlPath === "/anfrage/dichtung-auslegen-lassen" ? 0.95 :
        urlPath === "/wissen" || urlPath === "/werkstoffe" || urlPath === "/medien" ? 0.95 :
        urlPath.startsWith("/medien/") || urlPath.startsWith("/werkstoffe/") || urlPath.startsWith("/wissen/") ? 0.9 :
        0.7,
      alternateRefs: config.alternateRefs ?? [],
    };

    const lastmod = readContentDate(urlPath);
    if (lastmod) {
      entry.lastmod = lastmod;
    }

    return entry;
  },
};
