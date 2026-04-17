import { Metadata } from "next";
import { notFound } from "next/navigation";
import { getContentDoc, getAllSlugs } from "@/lib/content/loader";
import { createMetadata } from "@/lib/seo/metadata";
import { generateTechArticleSchema } from "@/lib/seo/jsonLd";
import MdxProse from "@/components/content/MdxProse";

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  const slugs = await getAllSlugs("medien");
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = await getContentDoc("medien", slug);
  if (!doc) return {};

  return createMetadata({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/medien/${slug}`,
    type: "article",
  });
}

export default async function MedienPage({ params }: Props) {
  const { slug } = await params;
  const doc = await getContentDoc("medien", slug);

  if (!doc) {
    notFound();
  }

  const jsonLd = generateTechArticleSchema({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/medien/${slug}`,
    category: "Chemische Beständigkeit / Medien",
  });

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <MdxProse content={doc.content} type="medien" slug={slug} />
    </>
  );
}
