import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Beaker, ShieldCheck } from "lucide-react";
import { getAllContentDocs } from "@/lib/content/loader";
import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema, generateCollectionPageSchema } from "@/lib/seo/jsonLd";

export const metadata: Metadata = createMetadata({
  title: "Dichtungswerkstoffe im konkreten Fall einordnen",
  description:
    "FKM, EPDM, NBR und PTFE nicht pauschal auswählen, sondern im konkreten Dichtungsfall prüfbar einordnen.",
  path: "/werkstoffe",
  image: DEFAULT_OG_IMAGE,
});

export default async function WerkstoffeIndexPage() {
  const docs = await getAllContentDocs("werkstoffe");
  const pageTitle = "Dichtungswerkstoffe im konkreten Fall einordnen";
  const pageDescription =
    "FKM, EPDM, NBR und PTFE nicht pauschal auswählen, sondern im konkreten Dichtungsfall prüfbar einordnen.";
  const collectionJsonLd = generateCollectionPageSchema({
    title: pageTitle,
    description: pageDescription,
    path: "/werkstoffe",
    items: docs.map((doc) => ({
      name: doc.metadata.title,
      path: `/werkstoffe/${doc.metadata.slug}`,
    })),
  });
  const breadcrumbJsonLd = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "Werkstoffe", path: "/werkstoffe" },
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
            <span className="font-medium text-foreground">Werkstoffe</span>
          </nav>
          <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
            Werkstoffcluster
          </span>
          <h1 className="mt-4 max-w-4xl text-4xl font-bold tracking-tight text-seal-blue md:text-6xl">
            Materialfragen werden erst im Fall sinnvoll
          </h1>
          <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground md:text-xl">
            EPDM, FKM, NBR und PTFE sind keine fertigen Antworten. sealingAI hilft, die Materialfrage
            mit Medium, Temperatur, Druck, Bewegung und Bauraum zu verbinden.
          </p>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="grid gap-5 sm:grid-cols-2">
            {docs.map((doc) => (
              <Link
                key={doc.metadata.slug}
                href={`/werkstoffe/${doc.metadata.slug}`}
                className="group flex min-h-[220px] flex-col justify-between rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
              >
                <div>
                  <Beaker className="text-seal-blue" size={28} />
                  <h2 className="mt-5 text-2xl font-bold text-seal-blue">{doc.metadata.title}</h2>
                  <p className="mt-3 leading-relaxed text-muted-foreground">{doc.metadata.description}</p>
                </div>
                <div className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-seal-blue">
                  Werkstoff ansehen
                  <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
                </div>
              </Link>
            ))}
          </div>

          <aside className="rounded-2xl border border-border bg-slate-50 p-8">
            <ShieldCheck className="text-seal-blue" size={34} />
            <h2 className="mt-5 text-2xl font-bold text-seal-blue">Orientierung mit sichtbaren Grenzen</h2>
            <p className="mt-4 leading-relaxed text-muted-foreground">
              sealingAI macht Werkstoffrichtungen prüfbar, ohne eine finale Eignung zu behaupten. Die
              Herstellerfreigabe bleibt der entscheidende Schritt.
            </p>
            <Link
              href="/anfrage/dichtung-auslegen-lassen"
              className="mt-8 inline-flex items-center gap-2 rounded-full bg-seal-blue px-6 py-3 font-bold text-white transition-all hover:opacity-90 active:scale-95"
            >
              Fall klären
              <ArrowRight size={18} />
            </Link>
          </aside>
        </div>
      </section>
    </div>
  );
}
