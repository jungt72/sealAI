import { getContentDoc } from "@/lib/content/loader";
import { ogImageContentType, ogImageSize, renderArticleOgImage } from "@/lib/seo/ogImage";

export const size = ogImageSize;
export const contentType = ogImageContentType;

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = await getContentDoc("medien", slug);
  return renderArticleOgImage({ title: doc?.metadata.title ?? "sealingAI", eyebrow: "Medien" });
}
