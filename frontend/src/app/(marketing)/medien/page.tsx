import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Droplets, FlaskConical } from "lucide-react";
import { getAllContentDocs } from "@/lib/content/loader";
import { createMetadata } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema, generateCollectionPageSchema } from "@/lib/seo/jsonLd";

export const metadata: Metadata = createMetadata({
  title: "Dichtungen nach Medium fallbezogen klären",
  description:
    "Öl, Dampf, Wasserstoff oder Chemikalien im konkreten Dichtungsfall einordnen und bessere Herstellerfragen vorbereiten.",
  path: "/medien",
});

export default async function MedienIndexPage() {
  const docs = await getAllContentDocs("medien");
  const pageTitle = "Dichtungen nach Medium fallbezogen klären";
  const pageDescription =
    "Öl, Dampf, Wasserstoff oder Chemikalien im konkreten Dichtungsfall einordnen und bessere Herstellerfragen vorbereiten.";
  const collectionJsonLd = generateCollectionPageSchema({
    title: pageTitle,
    description: pageDescription,
    path: "/medien",
    items: docs.map((doc) => ({
      name: doc.metadata.title,
      path: `/medien/${doc.metadata.slug}`,
    })),
  });
  const breadcrumbJsonLd = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "Medien", path: "/medien" },
  ]);

  return (
    <div className="flex flex-col">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(collectionJsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />
      <section className="border-b border-border/50 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
            <Link href="/" className="font-medium hover:text-seal-blue">
              Startseite
            </Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-foreground">Medien</span>
          </nav>
          <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
            Mediencluster
          </span>
          <h1 className="mt-4 max-w-4xl text-4xl font-bold tracking-tight text-seal-blue md:text-6xl">
            Ein Medium ist erst mit Betriebsdaten aussagefähig
          </h1>
          <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground md:text-xl">
            Öl, Dampf, Wasserstoff oder Chemikalie reichen als Stichwort selten aus. sealingAI zeigt,
            welche Mediumdetails für deinen Dichtungsfall wirklich fehlen.
          </p>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[0.85fr_1.15fr]">
          <aside className="rounded-2xl border border-border bg-seal-blue p-8 text-white">
            <FlaskConical className="text-seal-light-blue" size={34} />
            <h2 className="mt-5 text-2xl font-bold">Medium ist nicht nur ein Name</h2>
            <p className="mt-4 leading-relaxed text-seal-light-blue">
              Konzentration, Additive, Verschmutzung, Temperaturfenster und Druckspitzen können die
              Prüfung eines Dichtungswerkstoffs deutlich verändern.
            </p>
            <Link
              href="/werkstoffe"
              className="mt-8 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 font-bold text-seal-blue transition-all hover:bg-seal-light-blue active:scale-95"
            >
              Werkstoffe einordnen
              <ArrowRight size={18} />
            </Link>
          </aside>

          <div className="grid gap-5">
            {docs.map((doc) => (
              <Link
                key={doc.metadata.slug}
                href={`/medien/${doc.metadata.slug}`}
                className="group rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <Droplets className="text-seal-blue" size={28} />
                    <h2 className="mt-5 text-2xl font-bold text-seal-blue">{doc.metadata.title}</h2>
                    <p className="mt-3 leading-relaxed text-muted-foreground">{doc.metadata.description}</p>
                  </div>
                  <ArrowRight
                    className="shrink-0 text-seal-blue transition-transform group-hover:translate-x-1"
                    size={22}
                  />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
