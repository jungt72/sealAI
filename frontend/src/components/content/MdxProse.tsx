"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { ArrowRight, Info } from "lucide-react";
import { trackProductEvent } from "@/lib/analytics/events";
import { cn } from "@/lib/utils";

interface MdxProseProps {
  content: string;
  type: "medien" | "werkstoffe" | "wissen";
  slug: string;
  title: string;
}

type RelatedLink = {
  href: string;
  label: string;
  description: string;
};

const RELATED_LINKS: Record<string, RelatedLink[]> = {
  "wissen/wellendichtring": [
    { href: "/wissen/radialwellendichtring-din-3760", label: "Radialwellendichtring DIN 3760", description: "Normkontext, Bauformen und Anfrageparameter einordnen." },
    { href: "/wissen/wellendichtring-masse", label: "Wellendichtring Maße", description: "Abmessungen und offene Betriebsdaten für die Anfrage erfassen." },
    { href: "/wissen/wellendichtring-undicht", label: "Wellendichtring undicht", description: "Fehlerbild und mögliche Ursachen strukturiert erfassen." },
  ],
  "wissen/radialwellendichtring-din-3760": [
    { href: "/wissen/wellendichtring", label: "Wellendichtring Grundlagen", description: "Funktion, Grenzen und Betriebsdaten im Gesamtbild verstehen." },
    { href: "/wissen/radialwellendichtring-bauform", label: "Radialwellendichtring Bauform", description: "Staublippe, Mantel, Druck und Einbauraum vorprüfen." },
    { href: "/wissen/wellendichtring-masse", label: "Wellendichtring Maße", description: "Maßangaben sauber für Herstelleranfragen vorbereiten." },
  ],
  "wissen/wellendichtring-masse": [
    { href: "/wissen/wellendichtring", label: "Wellendichtring Grundlagen", description: "Maßangaben mit Funktion, Medium und Betriebsdaten verbinden." },
    { href: "/wissen/radialwellendichtring-din-3760", label: "DIN-3760-Kontext", description: "Normbezug und Anfrageparameter richtig einordnen." },
    { href: "/wissen/radialwellendichtring-bauform", label: "Bauform klären", description: "Warum gleiche Maße nicht automatisch gleiche Eignung bedeuten." },
  ],
  "wissen/radialwellendichtring-bauform": [
    { href: "/wissen/radialwellendichtring-din-3760", label: "Radialwellendichtring DIN 3760", description: "Norm- und Maßkontext für die technische Anfrage verstehen." },
    { href: "/wissen/wellendichtring-masse", label: "Wellendichtring Maße", description: "Wellendurchmesser, Gehäuse und Breite richtig erfassen." },
    { href: "/werkstoffe/nbr", label: "NBR-Dichtung", description: "Häufiger Standardwerkstoff für ölnahe Wellendichtringe." },
  ],
  "wissen/wellendichtring-undicht": [
    { href: "/wissen/wellendichtring", label: "Wellendichtring Grundlagen", description: "Kontaktzone, Schmierung, Druck und Montage im Kontext sehen." },
    { href: "/wissen/wellendichtring-ausfall", label: "Wellendichtring Ausfall", description: "Ausfallbilder und Prüfpunkte strukturiert erfassen." },
    { href: "/wissen/dichtung-schadensanalyse", label: "Dichtung Schadensanalyse", description: "Fehlerbild und Betriebsdaten für eine Prüfung dokumentieren." },
  ],
  "wissen/wellendichtring-ausfall": [
    { href: "/wissen/wellendichtring-undicht", label: "Wellendichtring undicht", description: "Leckage als konkretes Fehlerbild weiter eingrenzen." },
    { href: "/wissen/dichtung-schadensanalyse", label: "Dichtung Schadensanalyse", description: "Fotos, Betriebsdaten und offene Fragen dokumentieren." },
    { href: "/wissen/dichtung-temperatur-druck", label: "Temperatur und Druck", description: "Betriebsdaten als Ausfalltreiber sauber erfassen." },
  ],
  "wissen/dichtung-schadensanalyse": [
    { href: "/wissen/wellendichtring-undicht", label: "Wellendichtring undicht", description: "Leckageursachen an rotierenden Dichtstellen eingrenzen." },
    { href: "/wissen/wellendichtring-ausfall", label: "Wellendichtring Ausfall", description: "Typische Ausfallbilder und Prüffragen einordnen." },
    { href: "/wissen/dichtung-anfrage-vorbereiten", label: "Dichtung Anfrage vorbereiten", description: "Aus Schadensdaten eine prüfbare Anfragebasis machen." },
  ],
  "wissen/dichtung-anfrage-vorbereiten": [
    { href: "/anfrage/dichtung-auslegen-lassen", label: "Dichtung auslegen lassen", description: "Die strukturierte RFQ-Seite für hohe Anfrageintention." },
    { href: "/wissen/dichtung-temperatur-druck", label: "Temperatur und Druck", description: "Kernparameter für jede Herstellerprüfung erfassen." },
    { href: "/wissen/dichtung-schadensanalyse", label: "Dichtung Schadensanalyse", description: "Fehlerfälle sauber für Hersteller oder Spezialisten vorbereiten." },
  ],
  "wissen/dichtung-temperatur-druck": [
    { href: "/wissen/dichtung-medium-temperatur", label: "Medium und Temperatur", description: "Medienwirkung und Temperaturfenster zusammen bewerten." },
    { href: "/wissen/dichtung-anfrage-vorbereiten", label: "Dichtung Anfrage vorbereiten", description: "Betriebsdaten in eine prüfbare Anfragebasis überführen." },
    { href: "/medien/dichtung-dampf", label: "Dichtung für Dampf", description: "Druck, Temperatur und Kondensat als kritische Kombination." },
  ],
  "wissen/dichtung-medium-temperatur": [
    { href: "/wissen/dichtung-temperatur-druck", label: "Temperatur und Druck", description: "Betriebsdaten für Werkstoff- und Dichtungsprüfung klären." },
    { href: "/medien/dichtung-chemikalienbestaendig", label: "Chemikalienbeständige Dichtung", description: "Medium, Konzentration und Kontaktzeit strukturiert erfassen." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Werkstoffrichtung für chemische Anforderungen einordnen." },
  ],
  "wissen/gleitringdichtung-grundlagen": [
    { href: "/medien/dichtung-dampf", label: "Dichtung für Dampf", description: "Dampf, Kondensat und Zyklen als Belastungsfall verstehen." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Chemische Beständigkeit und konstruktive Grenzen einordnen." },
    { href: "/anfrage/dichtung-auslegen-lassen", label: "Anfrage strukturiert vorbereiten", description: "Betriebsdaten für eine Herstellerprüfung zusammenführen." },
  ],
  "werkstoffe/epdm": [
    { href: "/medien/dichtung-dampf", label: "Dichtung für Dampf", description: "EPDM im Dampf- und Heißwasser-Kontext kritisch einordnen." },
    { href: "/werkstoffe/fkm-vs-epdm", label: "FKM vs EPDM", description: "Öl, Wasser, Temperatur und Medienprofile vergleichen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Alternative für andere Medien- und Temperaturprofile vergleichen." },
  ],
  "werkstoffe/fkm": [
    { href: "/werkstoffe/viton-dichtung", label: "Viton-Dichtung", description: "Handelsname, FKM-Bezug und Prüfgrenzen einordnen." },
    { href: "/werkstoffe/nbr-vs-fkm", label: "NBR vs FKM", description: "Ölnahe Anwendungen und Temperaturgrenzen differenzieren." },
    { href: "/werkstoffe/fkm-vs-epdm", label: "FKM vs EPDM", description: "Wasser-, Dampf- und Ölkontexte voneinander trennen." },
  ],
  "werkstoffe/viton-dichtung": [
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Viton im breiteren FKM-Kontext fachlich einordnen." },
    { href: "/werkstoffe/nbr-vs-fkm", label: "NBR vs FKM", description: "Öl, Temperatur und Additive als Vergleichsbasis." },
    { href: "/medien/dichtung-oel", label: "Dichtung für Öl", description: "Ölkontext für Viton/FKM-Anfragen strukturieren." },
  ],
  "werkstoffe/nbr": [
    { href: "/werkstoffe/nbr-vs-fkm", label: "NBR vs FKM", description: "Öl, Temperatur und Additive strukturiert vergleichen." },
    { href: "/medien/dichtung-oel", label: "Dichtung für Öl", description: "Ölkontext und Additive für die Herstellerprüfung strukturieren." },
    { href: "/wissen/wellendichtring", label: "Wellendichtring", description: "Typische Anwendung von NBR im rotierenden Dichtfall verstehen." },
  ],
  "werkstoffe/ptfe": [
    { href: "/werkstoffe/ptfe-vs-fkm", label: "PTFE vs FKM", description: "Dichtungsverhalten, Medien und Rückstellung differenzieren." },
    { href: "/medien/dichtung-chemikalienbestaendig", label: "Chemikalienbeständige Dichtung", description: "Chemische Prüfdaten und Werkstoffrichtung klären." },
    { href: "/medien/salzsaeure", label: "Dichtung für Salzsäure", description: "Chemische Beständigkeit und Konzentration differenziert betrachten." },
  ],
  "werkstoffe/fkm-vs-epdm": [
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "FKM/Viton im Detail für Temperatur und Medien einordnen." },
    { href: "/werkstoffe/epdm", label: "EPDM-Dichtung", description: "EPDM in Wasser-, Wetter- und Dampf-nahem Kontext prüfen." },
    { href: "/medien/dichtung-dampf", label: "Dichtung für Dampf", description: "Dampf als kritischen Betriebsfall strukturiert erfassen." },
  ],
  "werkstoffe/ptfe-vs-fkm": [
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Chemische Orientierung und konstruktive Grenzen verstehen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Elastomerische Alternative für viele Medienprofile prüfen." },
    { href: "/medien/salzsaeure", label: "Dichtung für Salzsäure", description: "Chemische Belastung nach Konzentration und Temperatur betrachten." },
  ],
  "werkstoffe/nbr-vs-fkm": [
    { href: "/werkstoffe/nbr", label: "NBR-Dichtung", description: "Ölnahe Standardanwendungen und Grenzen einordnen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Höhere Temperatur- und Medienanforderungen prüfen." },
    { href: "/medien/dichtung-oel", label: "Dichtung für Öl", description: "Öltyp und Additive als Entscheidungsbasis klären." },
  ],
  "werkstoffe/o-ring-material": [
    { href: "/werkstoffe/nbr", label: "NBR-Dichtung", description: "Ölnahe O-Ring-Anwendungen als Werkstoffrichtung prüfen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Temperatur und Medienprofil für O-Ringe einordnen." },
    { href: "/werkstoffe/epdm", label: "EPDM-Dichtung", description: "Wasser- und Dampf-nahe O-Ring-Kontexte differenzieren." },
  ],
  "medien/dichtung-öl": [
    { href: "/werkstoffe/nbr", label: "NBR-Dichtung", description: "Häufiger Ausgangspunkt für viele ölnahe Anwendungen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Option bei höherer Temperatur oder anspruchsvollerem Medium." },
    { href: "/werkstoffe/nbr-vs-fkm", label: "NBR vs FKM", description: "Werkstoffvergleich für Öl, Temperatur und Additive." },
  ],
  "medien/dichtung-dampf": [
    { href: "/werkstoffe/epdm", label: "EPDM-Dichtung", description: "Dampf-nahe Einsatzfelder und Prüfgrenzen betrachten." },
    { href: "/wissen/dichtung-temperatur-druck", label: "Temperatur und Druck", description: "Betriebsdaten für Dampf-Anfragen sauber erfassen." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Konstruktive und thermische Anforderungen differenzieren." },
  ],
  "medien/salzsäure": [
    { href: "/medien/dichtung-chemikalienbestaendig", label: "Chemikalienbeständige Dichtung", description: "Konzentration, Temperatur und Kontaktzeit als Prüfbasis." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Chemische Beständigkeit und Kaltfluss im Kontext prüfen." },
    { href: "/werkstoffe/fkm", label: "FKM-Dichtung", description: "Konzentration, Temperatur und konkrete Rezeptur beachten." },
  ],
  "medien/dichtung-chemikalienbeständig": [
    { href: "/medien/salzsaeure", label: "Dichtung für Salzsäure", description: "Konkreten Chemikalienfall differenziert einordnen." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Chemische Beständigkeit und konstruktive Grenzen betrachten." },
    { href: "/wissen/dichtung-medium-temperatur", label: "Medium und Temperatur", description: "Medienwirkung und Temperaturfenster zusammen klären." },
  ],
  "medien/dichtung-wasserstoff": [
    { href: "/werkstoffe/epdm", label: "EPDM-Dichtung", description: "Werkstoffrichtung im Druck- und Temperaturkontext prüfen." },
    { href: "/werkstoffe/ptfe", label: "PTFE-Dichtung", description: "Permeation, Rückstellung und Konstruktion differenzieren." },
    { href: "/anfrage/dichtung-auslegen-lassen", label: "Wasserstoff-Anfrage vorbereiten", description: "Sicherheits- und Betriebsdaten herstellerprüfbar strukturieren." },
  ],
};

const TYPE_LABELS = {
  medien: "Medien",
  werkstoffe: "Werkstoffe",
  wissen: "Wissen",
};

export default function MdxProse({ content, type, slug, title }: MdxProseProps) {
  // Mapping for Context-Link
  const contextParam = type === "medien" ? "medium" : type === "werkstoffe" ? "material" : "context";
  const relatedLinks = RELATED_LINKS[`${type}/${slug}`] ?? [];
  const typeLabel = TYPE_LABELS[type];

  return (
    <article className="max-w-4xl mx-auto py-12 px-6">
      <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
        <Link href="/" className="font-medium hover:text-seal-blue">
          Startseite
        </Link>
        <span aria-hidden="true">/</span>
        <Link href={`/${type}`} className="font-medium hover:text-seal-blue">
          {typeLabel}
        </Link>
        <span aria-hidden="true">/</span>
        <span className="font-medium text-foreground">{title}</span>
      </nav>
      <div className="prose-clean">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ node, ...props }) => <h1 className="text-4xl font-bold mb-8 text-seal-blue border-b border-border pb-4" {...props} />,
            h2: ({ node, ...props }) => <h2 className="text-2xl font-bold mt-12 mb-6 text-seal-blue" {...props} />,
            h3: ({ node, ...props }) => <h3 className="text-xl font-bold mt-8 mb-4 text-seal-blue" {...props} />,
            p: ({ node, ...props }) => <p className="text-[17px] leading-relaxed mb-6 text-foreground/80" {...props} />,
            ul: ({ node, ...props }) => <ul className="list-disc pl-6 mb-8 space-y-3" {...props} />,
            ol: ({ node, ...props }) => <ol className="list-decimal pl-6 mb-8 space-y-3" {...props} />,
            li: ({ node, ...props }) => <li className="text-[17px] leading-relaxed" {...props} />,
            table: ({ node, ...props }) => (
              <div className="overflow-x-auto my-10 border border-border rounded-xl">
                <table className="w-full text-left text-sm border-collapse" {...props} />
              </div>
            ),
            thead: ({ node, ...props }) => <thead className="bg-slate-50 border-b border-border" {...props} />,
            th: ({ node, ...props }) => <th className="px-4 py-3 font-bold text-seal-blue uppercase tracking-wider text-[11px]" {...props} />,
            td: ({ node, ...props }) => <td className="px-4 py-3 border-b border-border/50 text-[14px]" {...props} />,
            blockquote: ({ node, ...props }) => (
              <blockquote className="border-l-4 border-seal-blue bg-slate-50 px-6 py-4 my-8 italic text-foreground/70" {...props} />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>

      {relatedLinks.length > 0 ? (
        <section className="mt-16 border-t border-border pt-10">
          <h2 className="text-2xl font-bold text-seal-blue">Weiterführende Einordnung</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {relatedLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="group flex min-h-[160px] flex-col justify-between rounded-2xl border border-border p-5 transition-all hover:border-seal-blue hover:shadow-lg"
              >
                <div>
                  <h3 className="text-base font-bold text-seal-blue">{link.label}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{link.description}</p>
                </div>
                <div className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-seal-blue">
                  Ansehen
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {/* DASHBOARD CTA */}
      <div className="mt-20 p-8 rounded-2xl bg-seal-blue text-white shadow-xl flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-white/10 rounded-xl">
            <Info size={28} className="text-seal-light-blue" />
          </div>
          <div>
            <h4 className="text-lg font-bold mb-1">Eigenen Dichtungsfall klären</h4>
            <p className="text-sm opacity-80 text-seal-light-blue">Nutze diese Einordnung als Startpunkt für deinen konkreten Fall. sealingAI zeigt, was bekannt ist und was noch fehlt.</p>
          </div>
        </div>
        <Link
          href={`/dashboard/new?${contextParam}=${slug}`}
          onClick={() =>
            trackProductEvent("pedia_to_case_clicked", {
              article_type: type,
              source: "article_cta",
              slug,
            })
          }
          className="group flex items-center gap-3 bg-white text-seal-blue px-6 py-3 rounded-full font-bold transition-all hover:bg-seal-light-blue active:scale-95 whitespace-nowrap"
        >
          <span>Fall jetzt klären</span>
          <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
        </Link>
      </div>
    </article>
  );
}
