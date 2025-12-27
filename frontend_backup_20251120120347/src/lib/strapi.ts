// frontend/src/lib/strapi.ts

const STRAPI_URL = (
  process.env.NEXT_PUBLIC_STRAPI_URL || "https://sealai.net"
).replace(/\/$/, "");

export type HomepageHero = {
  eyebrow: string | null;
  title: string | null;
  description: string | null;
  imageUrl: string | null;
  imageAlt: string | null;
};

type AnyRecord = Record<string, any>;

type StrapiResponse = {
  data?: AnyRecord | null;
  meta?: AnyRecord;
  error?: AnyRecord;
};

/**
 * Strapi v4: Eintrag hängt in data.attributes
 * Strapi v5: Eintrag hängt direkt in data
 */
function unwrapAttributes<T extends AnyRecord>(entry: T | null | undefined): T | null {
  if (!entry) return null;
  const attrs = (entry as AnyRecord).attributes;
  if (attrs && typeof attrs === "object") {
    return { ...(attrs as AnyRecord), ...entry } as T;
  }
  return entry;
}

/**
 * Media-Feld kann in Strapi:
 * - direkt ein Objekt sein
 * - ein Array sein
 * - oder ein Objekt mit .data / .data[]
 * und die eigentlichen Felder hängen ggf. wieder unter .attributes
 */
function getFirstMedia(entry: AnyRecord | null | undefined, key: string): AnyRecord | null {
  if (!entry) return null;
  const raw = entry[key];

  if (!raw) return null;

  // v4/v5: relation-ähnliche Struktur mit .data
  if (raw && typeof raw === "object" && "data" in raw) {
    const d = (raw as AnyRecord).data;
    if (Array.isArray(d)) {
      return d.length > 0 ? unwrapAttributes(d[0]) : null;
    }
    return unwrapAttributes(d);
  }

  // direktes Array
  if (Array.isArray(raw)) {
    return raw.length > 0 ? unwrapAttributes(raw[0]) : null;
  }

  // direktes Objekt
  if (typeof raw === "object") {
    return unwrapAttributes(raw as AnyRecord);
  }

  return null;
}

// ============================================================================
// AEROSPACE LANDING PAGE TYPES
// ============================================================================

export type NewsArticle = {
  id: string;
  title: string;
  excerpt: string;
  publishedDate: string;
  imageUrl: string;
  imageAlt: string;
  slug: string;
};

export type CompanyStat = {
  id: string;
  label: string;
  value: number;
  suffix?: string;
  prefix?: string;
};

export type NavigationItem = {
  id: string;
  label: string;
  href: string;
};

// ============================================================================
// MOCK DATA FUNCTIONS (for testing before Strapi connection)
// ============================================================================

export async function getNavigationItems(): Promise<NavigationItem[]> {
  // TODO: Replace with actual Strapi fetch
  return [
    { id: "1", label: "Products", href: "#products" },
    { id: "2", label: "Innovation", href: "#innovation" },
    { id: "3", label: "News", href: "#news" },
    { id: "4", label: "About", href: "#about" },
    { id: "5", label: "Contact", href: "#contact" },
  ];
}

export async function getLatestNews(): Promise<NewsArticle[]> {
  // TODO: Replace with actual Strapi fetch
  return [
    {
      id: "1",
      title: "Next-Generation Aircraft Platform Unveiled",
      excerpt: "Introducing our latest innovation in sustainable aviation technology, setting new standards for efficiency and performance.",
      publishedDate: "2025-11-15",
      imageUrl: "https://picsum.photos/seed/aerospace1/800/600",
      imageAlt: "Modern aircraft on runway",
      slug: "next-gen-platform",
    },
    {
      id: "2",
      title: "Partnership with Leading Technology Provider",
      excerpt: "Strategic collaboration to advance digital transformation and enhance operational excellence across our global operations.",
      publishedDate: "2025-11-10",
      imageUrl: "https://picsum.photos/seed/aerospace2/800/600",
      imageAlt: "Technology partnership announcement",
      slug: "tech-partnership",
    },
    {
      id: "3",
      title: "Sustainability Milestone Achieved",
      excerpt: "Reaching a significant milestone in our commitment to carbon-neutral operations and environmental responsibility.",
      publishedDate: "2025-11-05",
      imageUrl: "https://picsum.photos/seed/aerospace3/800/600",
      imageAlt: "Sustainable aviation initiative",
      slug: "sustainability-milestone",
    },
  ];
}

export async function getCompanyStats(): Promise<CompanyStat[]> {
  // TODO: Replace with actual Strapi fetch
  return [
    { id: "1", label: "Aircraft Delivered", value: 863, suffix: "+" },
    { id: "2", label: "Global Workforce", value: 45000, suffix: "+" },
    { id: "3", label: "Countries Served", value: 120, suffix: "+" },
    { id: "4", label: "R&D Investment", value: 2.8, prefix: "$", suffix: "B" },
  ];
}

export async function getAerospaceHero() {
  // TODO: Replace with actual Strapi fetch
  return {
    eyebrow: "Aerospace Corp",
    title: "Engineering the Future of Flight",
    description: "Leading innovation in aerospace technology with cutting-edge solutions for a sustainable tomorrow.",
    ctaText: "Explore Our Solutions",
    ctaHref: "#products",
    backgroundImage: "https://picsum.photos/seed/aerospace-hero/1920/1080",
  };
}

// ============================================================================
// EXISTING HOMEPAGE HERO FUNCTION
// ============================================================================

export async function getHomepageHero(): Promise<HomepageHero | null> {
  try {
    const res = await fetch(
      `${STRAPI_URL}/api/homepage?populate=deep`,
      {
        // ISR / Revalidation
        next: { revalidate: 60 },
        // Falls du irgendwann den v4-Response willst:
        // headers: { "Strapi-Response-Format": "v4" },
      }
    );

    if (!res.ok) {
      console.error(
        "Strapi homepage fetch failed:",
        res.status,
        res.statusText
      );
      return null;
    }

    const json = (await res.json()) as StrapiResponse;
    if (!json.data) {
      console.error("Strapi homepage: missing data in response");
      return null;
    }

    const data = unwrapAttributes(json.data);
    if (!data) {
      console.error("Strapi homepage: unwrapAttributes returned null");
      return null;
    }

    const eyebrow = (data as AnyRecord).heroEyebrow ?? null;
    const title = (data as AnyRecord).heroTitle ?? null;
    const description = (data as AnyRecord).heroDescription ?? null;

    const media = getFirstMedia(data, "homepage_hero");

    let rawUrl: string | null = null;
    if (media) {
      const formats = (media as AnyRecord).formats ?? {};
      rawUrl =
        formats?.large?.url ??
        formats?.medium?.url ??
        (media as AnyRecord).url ??
        null;
    }

    const imageUrl = rawUrl
      ? rawUrl.startsWith("http")
        ? rawUrl
        : `${STRAPI_URL}${rawUrl}`
      : null;

    const imageAlt =
      (media as AnyRecord)?.alternativeText ??
      (media as AnyRecord)?.name ??
      "SealAI hero background";

    return {
      eyebrow,
      title,
      description,
      imageUrl,
      imageAlt,
    };
  } catch (err) {
    console.error("Error fetching homepage hero from Strapi:", err);
    return null;
  }
}
