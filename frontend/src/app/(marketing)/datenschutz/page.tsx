import { Metadata } from "next";
import Link from "next/link";

import { createMetadata, DEFAULT_OG_IMAGE } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Datenschutzerklärung",
  description:
    "Datenschutzerklärung für sealingAI — Verantwortlicher, Verarbeitungszwecke, Rechtsgrundlagen, Betroffenenrechte.",
  path: "/datenschutz",
  image: DEFAULT_OG_IMAGE,
});

export default function DatenschutzPage() {
  return (
    <div className="flex flex-col">
      <section className="border-b border-border/50 py-16 md:py-20">
        <div className="mx-auto max-w-3xl px-6">
          <nav className="mb-8 flex flex-wrap items-center gap-2 text-sm text-muted-foreground" aria-label="Breadcrumb">
            <Link href="/" className="font-medium hover:text-seal-blue">
              Startseite
            </Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-foreground">Datenschutzerklärung</span>
          </nav>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Datenschutzerklärung
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Stand: 7. Juli 2026 · Fassung 2026-07-07-v1
          </p>
          <p className="mt-6 rounded-lg border border-border/60 bg-muted/30 p-4 text-sm leading-6 text-muted-foreground">
            Dieser Text ist ein Entwurf zur anwaltlichen Prüfung und beschreibt die Verarbeitung
            personenbezogener Daten im Zusammenhang mit sealingAI nach Art. 13/14
            Datenschutz-Grundverordnung (DSGVO).
          </p>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="mx-auto max-w-3xl space-y-12 px-6 text-[15px] leading-7 text-foreground/90">
          <article>
            <h2 className="text-xl font-semibold text-foreground">1. Verantwortlicher</h2>
            <p className="mt-3">
              Verantwortlicher im Sinne der DSGVO ist{" "}
              <span className="font-medium">
                [Platzhalter: Firma, Anschrift, E-Mail, ggf. Datenschutzbeauftragter/Kontakt]
              </span>
              .
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              2. Verarbeitungszwecke und Rechtsgrundlagen
            </h2>
            <p className="mt-3">
              Wir verarbeiten personenbezogene Daten für folgende Zwecke:
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>
                <span className="font-medium">Vertragsdurchführung</span> — Registrierung,
                Bereitstellung der Plattform, Nutzerverwaltung, Abrechnung (Art. 6 Abs. 1 lit. b
                DSGVO).
              </li>
              <li>
                <span className="font-medium">Nutzung der Kernfunktion</span> — Verarbeitung der
                von Ihnen eingegebenen Anfragen, hochgeladenen Dokumente und Fallangaben, um die in
                den Nutzungsbedingungen beschriebene Struktur-, Wissens- und Anfrageintelligenz zu
                erbringen (Art. 6 Abs. 1 lit. b DSGVO). Diese Verarbeitung schließt den Einsatz von
                KI-Modellen externer Anbieter ein (siehe Ziffer 5).
              </li>
              <li>
                <span className="font-medium">Sicherheit und Missbrauchsprävention</span> —
                Protokollierung, Fehleranalyse, Schutz vor missbräuchlicher Nutzung (Art. 6 Abs. 1
                lit. f DSGVO, berechtigtes Interesse an einem sicheren Betrieb).
              </li>
              <li>
                <span className="font-medium">Kommunikation mit Herstellern</span> — sofern Sie
                über die Plattform eine Anfrage (RFQ) an einen Herstellerpartner auslösen, wird der
                dafür erforderliche Ausschnitt Ihrer Falldaten an diesen Partner übermittelt (Art.
                6 Abs. 1 lit. b DSGVO, auf Ihre Veranlassung).
              </li>
              <li>
                <span className="font-medium">Reichweitenmessung und Produktanalyse</span> —
                ausschließlich soweit technisch nicht erforderliche Cookies/Tools eingesetzt und
                hierfür Einwilligung erteilt wurde (Art. 6 Abs. 1 lit. a DSGVO); siehe Ziffer 6.
              </li>
            </ul>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              3. Kategorien personenbezogener Daten
            </h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              <li>Stammdaten (Name, geschäftliche E-Mail-Adresse, Firma, Rolle, ggf. USt-IdNr.)</li>
              <li>Nutzungs- und Protokolldaten (u. a. IP-Adresse in gehashter Form, Zeitstempel, Fehlerprotokolle)</li>
              <li>
                Von Ihnen eingegebene Falldaten und hochgeladene Dokumente — diese können,
                abhängig vom Inhalt Ihrer Anfrage, technische, geschäftliche oder in Ausnahmefällen
                personenbezogene Angaben enthalten
              </li>
            </ul>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">4. Speicherdauer</h2>
            <p className="mt-3">
              Wir speichern personenbezogene Daten nur so lange, wie dies für die genannten Zwecke
              erforderlich ist oder gesetzliche Aufbewahrungspflichten bestehen. Falldaten bleiben
              tenant-gebunden — d. h. ausschließlich dem jeweiligen Unternehmen zugeordnet und von
              anderen Nutzern der Plattform isoliert — gespeichert, bis der Nutzer sie löscht oder
              das Vertragsverhältnis endet und keine gesetzliche Aufbewahrungspflicht entgegensteht.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              5. Empfänger, Auftragsverarbeiter, Drittlandtransfer
            </h2>
            <p className="mt-3">
              Zur Erbringung der Plattformfunktion setzen wir folgende Kategorien von
              Auftragsverarbeitern bzw. Diensten ein, mit denen jeweils eine
              Auftragsverarbeitungsvereinbarung nach Art. 28 DSGVO besteht bzw. abgeschlossen wird:
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              <li>
                <span className="font-medium">KI-Modell-Anbieter</span> (u. a. OpenAI) — zur
                Verarbeitung Ihrer Anfrage-Inhalte durch Sprachmodelle. Diese Verarbeitung kann eine
                Übermittlung in die USA einschließen; wir stützen diesen Transfer auf geeignete
                Garantien nach Art. 46 DSGVO (u. a. Standardvertragsklauseln).
              </li>
              <li>
                <span className="font-medium">Hosting-Infrastruktur</span> —{" "}
                <span className="font-medium">[Platzhalter: Hosting-Anbieter, Serverstandort]</span>.
              </li>
              <li>
                <span className="font-medium">Herstellerpartner</span> — nur bei aktiver Auslösung
                einer Anfrage (RFQ) durch Sie, beschränkt auf den dafür erforderlichen Inhalt.
              </li>
            </ul>
            <p className="mt-3">
              Eine vollständige, aktuelle Liste der eingesetzten Unterauftragsverarbeiter kann
              gesondert bereitgestellt werden (siehe Auftragsverarbeitungsvereinbarung).
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">
              6. Cookies, Analyse- und Marketing-Tools
            </h2>
            <p className="mt-3">
              Technisch notwendige Cookies (u. a. für Login und Sitzungsverwaltung) setzen wir auf
              Grundlage von Art. 6 Abs. 1 lit. f DSGVO ein. Für Reichweitenmessung und
              Produktanalyse können wir Google Tag Manager, Google Analytics sowie ein
              eigenständiges Analyse-Tool (Rybbit Analytics) einsetzen. Diese sind so konfiguriert,
              dass sie ohne Ihre Einwilligung standardmäßig deaktiviert sind (Consent-Mode „denied“)
              und erst nach erteilter Einwilligung aktiv werden.
            </p>
            <p className="mt-3 rounded-lg border border-border/60 bg-muted/30 p-4 text-sm text-muted-foreground">
              Offener Punkt (technisch): Eine nutzerseitige Consent-Banner-Oberfläche zur
              granularen Einwilligung ist zum Stand dieses Entwurfs noch nicht implementiert; bis
              zur Implementierung bleibt der Analyse-Consent auf „denied“ voreingestellt.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">7. Ihre Rechte</h2>
            <p className="mt-3">
              Sie haben nach Maßgabe der gesetzlichen Voraussetzungen das Recht auf Auskunft (Art.
              15 DSGVO), Berichtigung (Art. 16 DSGVO), Löschung (Art. 17 DSGVO), Einschränkung der
              Verarbeitung (Art. 18 DSGVO), Datenübertragbarkeit (Art. 20 DSGVO) sowie Widerspruch
              gegen die Verarbeitung (Art. 21 DSGVO). Erteilte Einwilligungen können Sie jederzeit
              mit Wirkung für die Zukunft widerrufen.
            </p>
            <p className="mt-3">
              Ihnen steht zudem ein Beschwerderecht bei einer Datenschutzaufsichtsbehörde zu,
              insbesondere in dem Mitgliedstaat Ihres gewöhnlichen Aufenthalts, Ihres Arbeitsplatzes
              oder des Orts des mutmaßlichen Verstoßes.
            </p>
          </article>

          <article>
            <h2 className="text-xl font-semibold text-foreground">8. Kontakt</h2>
            <p className="mt-3">
              Für Anfragen zum Datenschutz wenden Sie sich an{" "}
              <span className="font-medium">[Platzhalter: Datenschutz-Kontakt-E-Mail]</span>.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
