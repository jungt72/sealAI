import { Metadata } from "next";
import Link from "next/link";

import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Nutzungsbedingungen",
  description:
    "Nutzungsbedingungen für sealingAI — Geltungsbereich, Leistungsbeschreibung, Pflichten, Haftung.",
  path: "/nutzungsbedingungen",
  image: DEFAULT_OG_IMAGE,
});

export default function NutzungsbedingungenPage() {
  return (
    <div className="flex flex-col">
      <section className="border-b border-border/50 py-16 md:py-20">
        <div className="mx-auto max-w-3xl px-6">
          <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
            <Link href="/" className="font-medium hover:text-seal-blue">
              Startseite
            </Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-foreground">Nutzungsbedingungen</span>
          </nav>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Nutzungsbedingungen
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Stand: 7. Juli 2026 · Fassung 2026-07-07-v1
          </p>
          <p className="mt-6 rounded-lg border border-border/60 bg-muted/30 p-4 text-sm leading-6 text-muted-foreground">
            Diese Nutzungsbedingungen sind ein Entwurf zur anwaltlichen Prüfung und richten sich
            ausschließlich an Unternehmer im Sinne von § 14 BGB. sealingAI erbringt keine
            Rechtsberatung; dieser Text ersetzt keine individuelle rechtliche Prüfung durch den
            Anbieter oder seine Vertragspartner.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-12 px-6 text-[15px] leading-7 text-foreground/90">
          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 1 Geltungsbereich, Vertragspartner</h2>
            <p className="mt-3">
              (1) Diese Nutzungsbedingungen gelten für die Nutzung der Plattform sealingAI
              (nachfolgend „sealingAI“ oder „die Plattform“), betrieben von{" "}
              <span className="font-medium">[Platzhalter: Firma, Rechtsform, Anschrift]</span>{" "}
              (nachfolgend „Anbieter“), durch Unternehmer im Sinne von § 14 BGB (nachfolgend
              „Nutzer“). Eine Nutzung durch Verbraucher im Sinne von § 13 BGB ist nicht vorgesehen.
            </p>
            <p className="mt-3">
              (2) Der Nutzer bestätigt bei der Registrierung, dass die Nutzung im Rahmen seiner
              gewerblichen oder selbständigen beruflichen Tätigkeit erfolgt.
            </p>
            <p className="mt-3">
              (3) Abweichende, entgegenstehende oder ergänzende Geschäftsbedingungen des Nutzers
              werden nicht Vertragsbestandteil, es sei denn, der Anbieter stimmt ihrer Geltung
              ausdrücklich schriftlich zu.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 2 Leistungsbeschreibung</h2>
            <p className="mt-3">
              (1) sealingAI ist eine KI-gestützte Wissens-, Strukturierungs- und
              Anfrageintelligenz für Dichtungstechnik. Die Plattform unterstützt Nutzer bei der
              Extraktion und Strukturierung technischer Angaben, der Zuordnung von Parametern, der
              Auswertung hochgeladener Dokumente als Arbeitsgrundlage, der Vorbereitung von
              Anfragen (RFQs) an Hersteller, der Erklärung fachlicher Zusammenhänge sowie der
              Sichtbarmachung von Unsicherheiten in der jeweiligen Anwendungssituation.
            </p>
            <p className="mt-3 font-medium">
              (2) sealingAI ist keine technische Freigabe-, Auslegungs-, Gutachter- oder
              Produktempfehlungs-Software. Insbesondere erteilt sealingAI:
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              <li>keine technische Freigabe und keine verbindliche Auslegung,</li>
              <li>keine Werkstoff- oder Eignungsfreigabe,</li>
              <li>keine Normkonformitäts- oder Sicherheitsbewertung,</li>
              <li>keine Herstellerfreigabe,</li>
              <li>kein Prüfgutachten und</li>
              <li>keine verbindliche „geeignet“-Empfehlung.</li>
            </ul>
            <p className="mt-3">
              (3) Jede Ausgabe von sealingAI ist ein Arbeitsentwurf bzw. ein Anfrageentwurf. Die
              finale Werkstoff- und Auslegungsentscheidung sowie jede technische Freigabe trifft
              ausschließlich der Hersteller bzw. die verantwortliche Fachperson des Nutzers anhand
              des konkreten Datenblatts und der konkreten Einsatzbedingungen.
            </p>
            <p className="mt-3">
              (4) sealingAI setzt sprachbasierte KI-Modelle (Large Language Models) ein. Deren
              Ausgaben können fehlerhaft, unvollständig oder im Einzelfall unzutreffend sein. Der
              Nutzer ist verpflichtet, alle sicherheits- oder entscheidungsrelevanten Angaben vor
              Verwendung eigenständig fachlich zu prüfen bzw. prüfen zu lassen.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 3 Registrierung, Pflichten des Nutzers</h2>
            <p className="mt-3">
              (1) Die produktive Nutzung setzt eine Registrierung mit wahrheitsgemäßen
              geschäftlichen Angaben (Firma, geschäftliche E-Mail-Adresse, Rolle, ggf.
              USt-IdNr.) sowie die Bestätigung dieser Nutzungsbedingungen, der Datenschutzerklärung
              und — soweit personenbezogene Daten Dritter verarbeitet werden — der
              Auftragsverarbeitungsvereinbarung voraus.
            </p>
            <p className="mt-3">
              (2) Der Nutzer ist verpflichtet, Zugangsdaten geheim zu halten, die Plattform nicht
              missbräuchlich oder rechtswidrig zu nutzen und keine Inhalte hochzuladen, an denen er
              keine ausreichenden Rechte hat oder deren Verarbeitung gegen geltendes Recht
              verstößt.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 4 Nutzungsrechte</h2>
            <p className="mt-3">
              Der Anbieter räumt dem Nutzer für die Vertragslaufzeit ein einfaches, nicht
              übertragbares, nicht unterlizenzierbares Recht ein, die Plattform im vereinbarten
              Umfang für eigene betriebliche Zwecke zu nutzen.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 5 Verfügbarkeit, Änderungen</h2>
            <p className="mt-3">
              (1) Der Anbieter ist bestrebt, eine hohe Verfügbarkeit der Plattform zu erreichen;
              eine bestimmte Verfügbarkeit wird — soweit nicht individuell schriftlich vereinbart —
              nicht zugesichert. Wartungsfenster, Störungen bei vorgelagerten Diensten (u. a.
              KI-Modell-Anbietern) sowie höhere Gewalt können die Verfügbarkeit beeinträchtigen.
            </p>
            <p className="mt-3">
              (2) Der Anbieter kann Funktionen der Plattform weiterentwickeln, anpassen oder
              einstellen, soweit dies dem Nutzer unter Berücksichtigung seiner berechtigten
              Interessen zumutbar ist.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 6 Haftung</h2>
            <p className="mt-3">
              (1) Der Anbieter haftet unbeschränkt für Schäden aus der Verletzung des Lebens, des
              Körpers oder der Gesundheit, für Vorsatz und grobe Fahrlässigkeit, im Rahmen einer
              ausdrücklich übernommenen Garantie, nach den Vorschriften des
              Produkthaftungsgesetzes sowie in allen weiteren Fällen zwingender gesetzlicher
              Haftung.
            </p>
            <p className="mt-3">
              (2) Bei leicht fahrlässiger Verletzung wesentlicher Vertragspflichten
              (Kardinalpflichten — d. h. Pflichten, deren Erfüllung die ordnungsgemäße
              Durchführung des Vertrags überhaupt erst ermöglicht und auf deren Einhaltung der
              Nutzer regelmäßig vertrauen darf) haftet der Anbieter
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              <li>
                bei entgeltlicher Nutzung der Plattform der Höhe nach begrenzt auf die vom Nutzer
                in den letzten zwölf Monaten vor dem schadensauslösenden Ereignis tatsächlich
                gezahlte Vergütung, höchstens jedoch auf 25.000 EUR je Schadensfall;
              </li>
              <li>
                bei unentgeltlicher, Beta- oder Pilot-Nutzung der Höhe nach begrenzt auf höchstens
                1.000 EUR je Schadensfall.
              </li>
            </ul>
            <p className="mt-3">
              (3) Im Übrigen — d. h. bei leichter Fahrlässigkeit außerhalb der Verletzung
              wesentlicher Vertragspflichten — ist die Haftung des Anbieters ausgeschlossen. Ein
              darüberhinausgehender, pauschaler Haftungsausschluss ist mit dieser Regelung nicht
              verbunden; die Absätze 1 und 2 bleiben in jedem Fall unberührt.
            </p>
            <p className="mt-3">
              (4) Die vorstehenden Haftungsbegrenzungen gelten auch zugunsten der Erfüllungs- und
              Verrichtungsgehilfen des Anbieters.
            </p>
            <p className="mt-3">
              (5) Da sealingAI ausdrücklich keine technische Freigabe, Auslegung oder Eignungsprüfung
              vornimmt (§ 2), haftet der Anbieter nicht für Schäden, die daraus resultieren, dass
              ein Nutzer einen Arbeits- oder Anfrageentwurf ohne die in § 2 Abs. 4 vorgesehene
              eigene fachliche Prüfung als finale technische Entscheidung verwendet.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 7 Vertragslaufzeit, Kündigung</h2>
            <p className="mt-3">
              Laufzeit und Kündigungsfristen richten sich nach der jeweils gebuchten
              Leistungsbeschreibung. Das Recht zur außerordentlichen Kündigung aus wichtigem Grund
              bleibt unberührt.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">§ 8 Schlussbestimmungen</h2>
            <p className="mt-3">
              (1) Es gilt das Recht der Bundesrepublik Deutschland unter Ausschluss des
              UN-Kaufrechts.
            </p>
            <p className="mt-3">
              (2) Ausschließlicher Gerichtsstand für alle Streitigkeiten aus oder im Zusammenhang
              mit diesem Vertrag ist, soweit gesetzlich zulässig,{" "}
              <span className="font-medium">[Platzhalter: Sitz des Anbieters]</span>.
            </p>
            <p className="mt-3">
              (3) Sollten einzelne Bestimmungen dieser Nutzungsbedingungen unwirksam sein oder
              werden, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
