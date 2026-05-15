import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CheckCircle2 } from "lucide-react";
import { getAllContentDocs } from "@/lib/content/loader";
import { createMetadata } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema, generateCollectionPageSchema } from "@/lib/seo/jsonLd";

export const metadata: Metadata = createMetadata({
  title: "SealingPedia: Dichtungswissen für konkrete Fälle",
  description:
    "SealingPedia bündelt fachliche Orientierung für konkrete Dichtungsfälle: Begriffe, Schadensbilder, Normbezug und bessere Herstellerfragen.",
  path: "/wissen",
});

const principles = [
  "Betriebsdaten vor Produktempfehlung",
  "Normbezug und Einsatzgrenzen klar benennen",
  "Offene Prüfpunkte für Hersteller sichtbar machen",
];

export default async function WissenIndexPage() {
  const docs = await getAllContentDocs("wissen");
  const pageTitle = "SealingPedia: Dichtungswissen für konkrete Fälle";
  const pageDescription =
    "SealingPedia bündelt fachliche Orientierung für konkrete Dichtungsfälle: Begriffe, Schadensbilder, Normbezug und bessere Herstellerfragen.";
  const collectionJsonLd = generateCollectionPageSchema({
    title: pageTitle,
    description: pageDescription,
    path: "/wissen",
    items: docs.map((doc) => ({
      name: doc.metadata.title,
      path: `/wissen/${doc.metadata.slug}`,
    })),
  });
  const breadcrumbJsonLd = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "SealingPedia", path: "/wissen" },
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
            <span className="font-medium text-foreground">SealingPedia</span>
          </nav>
          <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
            SealingPedia
          </span>
          <h1 className="mt-4 max-w-4xl text-4xl font-bold tracking-tight text-seal-blue md:text-6xl">
            SealingPedia: Dichtungswissen, das deinen Fall klärbarer macht
          </h1>
          <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground md:text-xl">
            Keine Lexikontexte ohne Anschluss. Jede Einordnung soll dir helfen, bessere Fragen zu stellen,
            offene Punkte zu erkennen und souveräner mit Herstellern oder Kollegen zu sprechen.
          </p>
          <div className="mt-8">
            <Link
              href="/rag"
              className="inline-flex items-center gap-2 rounded-full border border-[#D9E5F7] bg-white px-5 py-2.5 text-sm font-semibold text-[#0B57D0] shadow-sm transition hover:bg-[#F8FBFF]"
            >
              Markdown für SealingPedia hochladen
              <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[0.75fr_1.25fr]">
          <aside className="rounded-2xl border border-border bg-slate-50 p-8">
            <BookOpen className="text-seal-blue" size={34} />
            <h2 className="mt-5 text-2xl font-bold text-seal-blue">SealingPedia statt Scheinsicherheit</h2>
            <p className="mt-4 leading-relaxed text-muted-foreground">
              Die SealingPedia-Seiten machen dich aussagefähig. Sie ersetzen keine finale Auslegung,
              Materialfreigabe oder Herstellerprüfung.
            </p>
            <div className="mt-6 space-y-3">
              {principles.map((principle) => (
                <div key={principle} className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 shrink-0 text-seal-blue" size={18} />
                  <span className="text-sm font-medium text-foreground">{principle}</span>
                </div>
              ))}
            </div>
          </aside>

          <div className="grid gap-5">
            {docs.map((doc) => (
              <Link
                key={doc.metadata.slug}
                href={`/wissen/${doc.metadata.slug}`}
                className="group rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-2xl font-bold text-seal-blue">{doc.metadata.title}</h2>
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
