import { Metadata } from "next";
import { notFound } from "next/navigation";
import { getContentDoc, getAllSlugs } from "@/lib/content/loader";
import { createMetadata } from "@/lib/seo/metadata";
import { generateArticleSchema } from "@/lib/seo/jsonLd";
import MdxProse from "@/components/content/MdxProse";

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  const slugs = await getAllSlugs("wissen");
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = await getContentDoc("wissen", slug);
  if (!doc) return {};

  return createMetadata({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/wissen/${slug}`,
    type: "article",
  });
}

export default async function WissenPage({ params }: Props) {
  const { slug } = await params;
  const doc = await getContentDoc("wissen", slug);

  if (!doc) {
    notFound();
  }

  const jsonLd = generateArticleSchema({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/wissen/${slug}`,
    datePublished: doc.metadata.datePublished,
    author: doc.metadata.author,
  });

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <MdxProse content={doc.content} type="wissen" slug={slug} />
    </>
  );
}
