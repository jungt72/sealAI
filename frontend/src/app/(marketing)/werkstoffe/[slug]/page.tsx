import { Metadata } from "next";
import { notFound } from "next/navigation";
import { formatContentDate, getContentDoc, getAllSlugs } from "@/lib/content/loader";
import { createMetadata } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema, generateTechArticleSchema } from "@/lib/seo/jsonLd";
import MdxProse from "@/components/content/MdxProse";

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  const slugs = await getAllSlugs("werkstoffe");
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = await getContentDoc("werkstoffe", slug);
  if (!doc) return {};

  return createMetadata({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/werkstoffe/${slug}`,
    type: "article",
  });
}

export default async function WerkstoffePage({ params }: Props) {
  const { slug } = await params;
  const doc = await getContentDoc("werkstoffe", slug);

  if (!doc) {
    notFound();
  }

  const jsonLd = generateTechArticleSchema({
    title: doc.metadata.title,
    description: doc.metadata.description,
    path: `/werkstoffe/${slug}`,
    category: "Dichtungswerkstoffe / Elastomere",
    datePublished: doc.metadata.datePublished,
    dateModified: doc.metadata.dateModified,
  });
  const breadcrumbJsonLd = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "Werkstoffe", path: "/werkstoffe" },
    { name: doc.metadata.title, path: `/werkstoffe/${slug}` },
  ]);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />
      <MdxProse
        content={doc.content}
        type="werkstoffe"
        slug={slug}
        title={doc.metadata.title}
        dateLabel={formatContentDate(doc.metadata.dateModified)}
      />
    </>
  );
}
