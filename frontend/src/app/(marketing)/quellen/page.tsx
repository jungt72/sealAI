import { Metadata } from "next";
import Link from "next/link";

import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema } from "@/lib/seo/jsonLd";

export const metadata: Metadata = createMetadata({
  title: "Quellen und Prüfstatus",
  description:
    "Wie sealingAI Aussagen mit Evidenzstufen und Prüfstatus versieht — und welchen Stand die Wissensartikel aktuell haben.",
  path: "/quellen",
  image: DEFAULT_OG_IMAGE,
});

function JsonLd() {
  const schema = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "Quellen und Prüfstatus", path: "/quellen" },
  ]);
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />;
}

const LEVELS: { level: string; label: string; text: string }[] = [
  { level: "A", label: "Primärbeleg", text: "Norm oder belastbare veröffentlichte Prüfdaten." },
  { level: "B", label: "Herstellerangabe", text: "Herstellerdaten mit klar benannten Randbedingungen." },
  { level: "C", label: "Fachquellen", text: "Mehrere übereinstimmende unabhängige Fachquellen." },
  { level: "D", label: "Orientierungswert", text: "Allgemeiner Orientierungswert ohne belastbaren Einzelbeleg." },
  { level: "U", label: "Unzureichend belegt", text: "Wird nicht als Empfehlung ausgegeben." },
];

export default function QuellenPage() {
  return (
    <div className="flex flex-col">
      <JsonLd />
      <section className="border-b border-border/50 py-16 md:py-20">
        <div className="mx-auto max-w-3xl px-6">
          <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
            <Link href="/" className="font-medium hover:text-seal-blue">
              Startseite
            </Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-foreground">Quellen und Prüfstatus</span>
          </nav>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Quellen und Prüfstatus
          </h1>
          <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
            sealingAI unterscheidet, wie belastbar eine technische Aussage ist, statt Werkstoff- oder
            Anwendungswissen pauschal als sicher darzustellen.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-12 px-6 text-[15px] leading-7 text-foreground/90">
          <article>
            <h2 className="text-xl font-semibold text-foreground">Evidenzstufen</h2>
            <p className="mt-3">Jede Wissensaussage kann grundsätzlich einer dieser Stufen zugeordnet werden:</p>
            <div className="mt-5 space-y-3">
              {LEVELS.map((item) => (
                <div key={item.level} className="flex items-start gap-4 rounded-xl border border-border p-4">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-seal-light-blue text-sm font-bold text-seal-blue">
                    {item.level}
                  </span>
                  <div>
                    <p className="font-medium text-foreground">{item.label}</p>
                    <p className="mt-1 text-muted-foreground">{item.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Aktueller Stand der Wissensartikel</h2>
            <p className="mt-3">
              Diese Evidenzstufen sind Teil des Content-Datenmodells von sealingAI. Die bestehenden
              Wissens-, Werkstoff- und Medienartikel wurden vor Einführung dieser Systematik verfasst
              und tragen deshalb aktuell den Status <span className="font-medium text-foreground">„legacy&#8220;</span> —
              das heißt: Prüfstatus und Evidenzstufe sind für diese Artikel noch nicht einzeln
              erfasst. Das ist eine ehrliche Aussage über den Bearbeitungsstand, keine Aussage über
              falsche Inhalte. Artikel werden schrittweise auf das neue Modell überführt.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Was das für dich bedeutet</h2>
            <p className="mt-3">
              Bei einer konkreten technischen Entscheidung ersetzt kein Wissensartikel die Prüfung
              durch den Hersteller oder eine fachkundige Person. Mehr zur Arbeitsweise von sealingAI
              steht auf der{" "}
              <Link href="/methodik" className="font-medium text-seal-blue hover:underline">
                Methodik-Seite
              </Link>
              .
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
