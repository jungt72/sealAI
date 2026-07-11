import { Metadata } from "next";
import Link from "next/link";

import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";
import { generateBreadcrumbSchema } from "@/lib/seo/jsonLd";

export const metadata: Metadata = createMetadata({
  title: "Methodik: Wie sealingAI strukturiert und bewertet",
  description:
    "Wie sealingAI zwischen Kernel und Sprachmodell trennt, Unsicherheit sichtbar hält und warum die Plattform keine finale Materialfreigabe ausspricht.",
  path: "/methodik",
  image: DEFAULT_OG_IMAGE,
});

function JsonLd() {
  const schema = generateBreadcrumbSchema([
    { name: "Startseite", path: "/" },
    { name: "Methodik", path: "/methodik" },
  ]);
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />;
}

export default function MethodikPage() {
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
            <span className="font-medium text-foreground">Methodik</span>
          </nav>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Wie sealingAI strukturiert und bewertet
          </h1>
          <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
            sealingAI ist eine herstellerneutrale Vorbewertungsinstanz für Dichtungstechnik — keine
            finale technische Freigabeinstanz. Diese Seite beschreibt, wie das System intern
            arbeitet, damit die Grenzen der Plattform nachvollziehbar sind, nicht nur im
            Kleingedruckten stehen.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-12 px-6 text-[15px] leading-7 text-foreground/90">
          <article>
            <h2 className="text-xl font-semibold text-foreground">Kernel entscheidet, Sprachmodell formuliert</h2>
            <p className="mt-3">
              Zahlen, Grenzwerte und Berechnungen kommen ausschließlich aus einem deterministischen
              Rechenkern — nicht aus einem Sprachmodell. Der kostenlose{" "}
              <Link href="/anfrage/dichtung-auslegen-lassen" className="font-medium text-seal-blue hover:underline">
                Dichtungsfall-Vorcheck
              </Link>{" "}
              berechnet zum Beispiel die Umfangsgeschwindigkeit nach der Formel v = π·d·n/60000 direkt
              im Browser — ohne Sprachmodell, ohne Serveraufruf. Ein Sprachmodell erklärt und ordnet
              ein, erfindet aber keine Werte.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Vier Ebenen gegen Fehlinformation</h2>
            <p className="mt-3">
              Verlässlichkeit entsteht aus dem Zusammenspiel von vier Ebenen, nicht aus einer
              einzelnen Kontrolle:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>
                <span className="font-medium text-foreground">Generator</span> — verarbeitet den
                Fall und erklärt den Zusammenhang, erfindet aber keine Normwerte.
              </li>
              <li>
                <span className="font-medium text-foreground">Grounding</span> — stützt konkrete
                Aussagen auf strukturiertes Fachwissen mit Herkunftsnachweis, statt aus dem
                Gedächtnis zu antworten.
              </li>
              <li>
                <span className="font-medium text-foreground">Prüfung</span> — eine unabhängige
                zweite Instanz prüft die Antwort gegen bekannte Fehlerbilder, bevor sie ausgegeben
                wird.
              </li>
              <li>
                <span className="font-medium text-foreground">Mensch/Hersteller</span> — die
                Orientierung von sealingAI ersetzt keine verbindliche Freigabe. Die entscheidet der
                Hersteller oder die zuständige Fachperson.
              </li>
            </ul>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Unsicherheit ist ein Zustand, kein Textbaustein</h2>
            <p className="mt-3">
              sealingAI unterscheidet bei jeder Angabe, ob sie bestätigt, geschätzt, kritisch offen
              oder berechnet ist. Fehlende Angaben werden benannt, nicht stillschweigend angenommen.
              Das gilt für den kostenlosen Vorcheck genauso wie für die vollständige Analyse.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Werkstofffamilie orientiert, Bauteil wird freigegeben — aber nicht von uns</h2>
            <p className="mt-3">
              Eine Aussage wie „FKM ist für Medium X geeignet&#8220; ist ohne Konzentration, Temperatur,
              Compound und Betriebsbedingungen keine belastbare Aussage. sealingAI ordnet
              Werkstofffamilien ein, bewertet Compounds mit ihren Randbedingungen und macht sichtbar,
              was für eine echte Freigabe noch fehlt. Die Freigabe eines konkreten Bauteils bleibt
              beim Hersteller.
            </p>
          </article>

          <article id="redaktionelle-verantwortung" className="scroll-mt-20">
            <h2 className="text-xl font-semibold text-foreground">Redaktionelle Verantwortung</h2>
            <p className="mt-3">
              Die Inhalte dieser Website werden unter menschlicher redaktioneller Kontrolle erstellt
              und geprüft. Die redaktionelle Verantwortung im Sinne der Transparenzpflichten der
              EU-KI-Verordnung (Art. 50 Abs. 4) trägt{" "}
              <span className="font-medium text-foreground">Thorsten Jung</span>. Bei der Erstellung
              und Strukturierung von Inhalten kommen auch KI-gestützte Werkzeuge zum Einsatz — die
              inhaltliche Prüfung und Freigabe bleibt beim Menschen.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">Verwandt</h2>
            <p className="mt-3">
              Wie einzelne Aussagen mit Quellen und Prüfstatus versehen werden, steht auf der{" "}
              <Link href="/quellen" className="font-medium text-seal-blue hover:underline">
                Quellen- und Prüfstatus-Seite
              </Link>
              .
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
