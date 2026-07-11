import { Metadata } from "next";
import Link from "next/link";

import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Auftragsverarbeitungsvereinbarung (AVV)",
  description:
    "Auftragsverarbeitungsvereinbarung (AVV / DPA) für sealingAI nach Art. 28 DSGVO.",
  path: "/auftragsverarbeitung",
  image: DEFAULT_OG_IMAGE,
});

export default function AuftragsverarbeitungPage() {
  return (
    <div className="flex flex-col">
      <section className="border-b border-border/50 py-16 md:py-20">
        <div className="mx-auto max-w-3xl px-6">
          <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
            <Link href="/" className="font-medium hover:text-seal-blue">
              Startseite
            </Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-foreground">Auftragsverarbeitungsvereinbarung</span>
          </nav>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Auftragsverarbeitungsvereinbarung (AVV)
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Stand: 7. Juli 2026 · Fassung 2026-07-07-v1 · gemäß Art. 28 DSGVO
          </p>
          <p className="mt-6 rounded-lg border border-border/60 bg-muted/30 p-4 text-sm leading-6 text-muted-foreground">
            Dieser Text ist ein Entwurf zur anwaltlichen Prüfung. Er wird Vertragsbestandteil,
            sobald Sie ihn im Rahmen des Legal-Gate-Onboardings akzeptieren, und ergänzt die
            Nutzungsbedingungen für den Fall, dass im Rahmen der Nutzung personenbezogene Daten
            Dritter (z. B. Mitarbeitender Ihres Unternehmens) durch sealingAI im Auftrag
            verarbeitet werden.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-12 px-6 text-[15px] leading-7 text-foreground/90">
          <article>
            <h2 className="text-xl font-semibold text-foreground">1. Gegenstand und Dauer</h2>
            <p className="mt-3">
              Gegenstand dieser Vereinbarung ist die Verarbeitung personenbezogener Daten durch{" "}
              <span className="font-medium">[Platzhalter: Firma des Anbieters]</span> (nachfolgend
              „Auftragsverarbeiter“) im Auftrag des Nutzers (nachfolgend „Verantwortlicher“) im
              Rahmen der Nutzung der Plattform sealingAI. Die Dauer entspricht der Laufzeit des
              zugrundeliegenden Nutzungsvertrags.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              2. Art und Zweck der Verarbeitung
            </h2>
            <p className="mt-3">
              Die Verarbeitung umfasst die technische Strukturierung, Speicherung und Auswertung
              von Falldaten und ggf. hochgeladenen Dokumenten des Verantwortlichen zum Zweck der
              Bereitstellung der in den Nutzungsbedingungen (§ 2) beschriebenen Wissens-,
              Strukturierungs- und Anfrageintelligenz, einschließlich der hierfür erforderlichen
              Verarbeitung durch eingesetzte KI-Modelle (siehe Ziffer 6).
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              3. Art der Daten, Kategorien betroffener Personen
            </h2>
            <p className="mt-3">
              Art der Daten: Kontaktdaten, technische Falldaten, ggf. in hochgeladenen Dokumenten
              enthaltene personenbezogene Angaben. Kategorien betroffener Personen: Mitarbeitende
              und Ansprechpartner des Verantwortlichen, deren Daten im Rahmen der Nutzung anfallen.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              4. Pflichten des Auftragsverarbeiters
            </h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              <li>
                Verarbeitung ausschließlich auf dokumentierte Weisung des Verantwortlichen, es sei
                denn, eine gesetzliche Verpflichtung erfordert etwas anderes (Art. 28 Abs. 3 lit. a
                DSGVO).
              </li>
              <li>
                Sicherstellung, dass zur Verarbeitung befugte Personen der Vertraulichkeit
                unterliegen (Art. 28 Abs. 3 lit. b DSGVO).
              </li>
              <li>
                Umsetzung geeigneter technischer und organisatorischer Maßnahmen nach Art. 32
                DSGVO, insbesondere tenant-gebundene Datenisolierung (jede Anfrage und jeder Upload
                wird eindeutig einem Mandanten zugeordnet und ist von den Daten anderer Mandanten
                technisch getrennt), Verschlüsselung während der Übertragung sowie eine
                rollenbasierte Zugriffskontrolle.
              </li>
              <li>
                Unterstützung des Verantwortlichen bei der Erfüllung von Betroffenenrechten sowie
                bei Datenschutz-Folgenabschätzungen, soweit erforderlich (Art. 28 Abs. 3 lit. e, f
                DSGVO).
              </li>
              <li>
                Unverzügliche Meldung von Verletzungen des Schutzes personenbezogener Daten an den
                Verantwortlichen nach Kenntniserlangung (Art. 28 Abs. 3 lit. f i. V. m. Art. 33
                DSGVO).
              </li>
              <li>
                Löschung oder Rückgabe aller personenbezogenen Daten nach Beendigung der
                Erbringung der Verarbeitungsleistungen, sofern keine gesetzliche Pflicht zur
                Speicherung besteht (Art. 28 Abs. 3 lit. g DSGVO).
              </li>
              <li>
                Bereitstellung aller zum Nachweis der Einhaltung dieser Vereinbarung erforderlichen
                Informationen sowie Ermöglichung von Kontrollen im zumutbaren Rahmen (Art. 28 Abs. 3
                lit. h DSGVO).
              </li>
            </ul>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              5. Kein Training globaler Modelle mit Kundendaten
            </h2>
            <p className="mt-3">
              Vom Verantwortlichen eingegebene Falldaten und hochgeladene Dokumente werden nicht
              standardmäßig zum Training globaler, mandantenübergreifender Modelle verwendet und
              nicht ohne gesonderte, dokumentierte Freigabe des Verantwortlichen in die öffentliche
              Wissensbasis von sealingAI überführt. Die öffentliche Wissensbasis (kuratierte
              Fachinhalte zur Dichtungstechnik) ist von mandantengebundenen Falldaten technisch
              getrennt.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">6. Unterauftragsverarbeiter</h2>
            <p className="mt-3">
              Der Auftragsverarbeiter setzt zur Erbringung der Leistung folgende Kategorien von
              Unterauftragsverarbeitern ein: KI-Modell-Anbieter (u. a. OpenAI, Verarbeitung in den
              USA auf Grundlage geeigneter Garantien nach Art. 46 DSGVO) sowie
              Hosting-Infrastruktur ({" "}
              <span className="font-medium">[Platzhalter: Hosting-Anbieter, Serverstandort]</span>
              ). Der Verantwortliche erteilt hiermit seine allgemeine Zustimmung zum Einsatz dieser
              Kategorien von Unterauftragsverarbeitern; über den Austausch oder die Hinzuziehung
              weiterer Unterauftragsverarbeiter wird der Verantwortliche informiert und kann
              innerhalb einer angemessenen Frist widersprechen.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">7. Haftung</h2>
            <p className="mt-3">
              Für die Haftung im Rahmen dieser Vereinbarung gilt § 6 der Nutzungsbedingungen
              entsprechend.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">8. Laufzeit, Beendigung</h2>
            <p className="mt-3">
              Diese Vereinbarung gilt für die Dauer des zugrundeliegenden Nutzungsvertrags. Nach
              dessen Beendigung löscht oder gibt der Auftragsverarbeiter alle personenbezogenen
              Daten des Verantwortlichen nach dessen Wahl zurück, soweit keine gesetzliche Pflicht
              zur weiteren Speicherung besteht.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
