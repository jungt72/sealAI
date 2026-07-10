import fs from "node:fs/promises";
import path from "node:path";

export type ContentMetadata = {
  title: string;
  description: string;
  category?: string;
  datePublished?: string;
  /** Falls back to `datePublished` when the article has never been edited since. */
  dateModified?: string;
  author?: string;
  slug: string;
};

export type ContentDoc = {
  metadata: ContentMetadata;
  content: string;
};

const CONTENT_ROOT = path.join(process.cwd(), "content");

/**
 * Minimalist Frontmatter Parser
 * Extracts title and description from markdown head.
 */
function parseFrontmatter(fileContent: string, slug: string): ContentDoc {
  const lines = fileContent.split("\n");
  const metadata: Partial<ContentMetadata> = { slug };
  let contentStart = 0;

  if (lines[0]?.trim() === "---") {
    let i = 1;
    while (i < lines.length && lines[i]?.trim() !== "---") {
      const line = lines[i];
      const colonIndex = line.indexOf(":");
      if (colonIndex !== -1) {
        const key = line.slice(0, colonIndex).trim();
        const value = line.slice(colonIndex + 1).trim().replace(/^["']|["']$/g, "");
        (metadata as any)[key] = value;
      }
      i++;
    }
    contentStart = i + 1;
  }

  return {
    metadata: {
      title: metadata.title || "Titel fehlt",
      description: metadata.description || "Beschreibung fehlt",
      slug: metadata.slug || slug,
      category: metadata.category,
      datePublished: metadata.datePublished,
      dateModified: metadata.dateModified || metadata.datePublished,
      author: metadata.author,
    },
    content: lines.slice(contentStart).join("\n").trim(),
  };
}

export async function getContentDoc(type: "medien" | "werkstoffe" | "wissen", slug: string): Promise<ContentDoc | null> {
  try {
    const filePath = path.join(CONTENT_ROOT, type, `${slug}.md`);
    const fileContent = await fs.readFile(filePath, "utf-8");
    return parseFrontmatter(fileContent, slug);
  } catch (error) {
    console.error(`Content not found: ${type}/${slug}`, error);
    return null;
  }
}

export async function getAllSlugs(type: "medien" | "werkstoffe" | "wissen"): Promise<string[]> {
  try {
    const dirPath = path.join(CONTENT_ROOT, type);
    const files = await fs.readdir(dirPath);
    return files
      .filter((f) => f.endsWith(".md"))
      .sort()
      .map((f) => f.replace(".md", ""));
  } catch (error) {
    return [];
  }
}

export async function getAllContentDocs(type: "medien" | "werkstoffe" | "wissen"): Promise<ContentDoc[]> {
  const slugs = await getAllSlugs(type);
  const docs = await Promise.all(slugs.map((slug) => getContentDoc(type, slug)));

  return docs.filter((doc): doc is ContentDoc => Boolean(doc));
}

/** German-locale "Stand: 5. Mai 2026" formatting for the visible date shown on article pages. */
export function formatContentDate(dateStr: string | undefined): string | undefined {
  if (!dateStr) return undefined;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return undefined;
  return new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "long", year: "numeric" }).format(date);
}
