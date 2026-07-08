/**
 * sealingAI homepage content — single source of truth for the marketing copy.
 * Keeping the German copy here keeps the page component structural and lets the
 * FAQPage JSON-LD derive from the exact FAQ that is visibly rendered.
 *
 * No claims of final release, guaranteed suitability, or manufacturer approval.
 */

/** Analysis handoff: the auth-gated analysis workspace (served by frontend-v2). */
export const ANALYZE_HREF = "/dashboard/new";
/** Manufacturer partner enquiry. TODO(frontend): replace with a dedicated /partner route/form. */
export const PARTNER_HREF = "/kontakt";
export const TEASER_STORAGE_KEY = "sealingai.homepageTeaserState";

export const heroContent = {
  eyebrow: "Sealing Intelligence Platform",
  headline: "Dichtungstechnik ist Erfahrungswissenschaft.",
  subheadline: "sealingAI macht Erfahrung systematisch nutzbar.",
  description: [
    "Dichtungen scheitern selten an einem einzelnen Wert. Entscheidend ist das Zusammenspiel aus Medium, Temperatur, Druck, Bewegung, Oberfläche, Montage und Erfahrung.",
    "sealingAI strukturiert Ihren Dichtungsfall, erkennt fehlende Angaben, berechnet erste Kennwerte und erstellt daraus eine belastbare Grundlage für Auslegung, Beschaffung oder Herstelleranfrage.",
  ],
  strongSentence: "Aus unvollständigen Angaben wird ein technischer Fall.",
  trustLine: "Keine Produktwerbung. Keine Scheinsicherheit. Keine gekaufte technische Empfehlung.",
};

export const realityCheck = {
  id: "reality-check",
  headline: "Warum Dichtungsfälle oft falsch starten",
  intro: ["In vielen Anfragen steht:", "„Öl, 80 °C, 10 bar.“", "Das klingt eindeutig. Ist es aber selten."],
  lead: "Denn für eine Dichtung zählen oft genau die Punkte, die nicht in der ersten Anfrage stehen:",
  points: [
    "Gibt es Druckspitzen?",
    "Ist das Medium wirklich bekannt?",
    "Welche Additive oder Reinigungsmedien kommen vor?",
    "Gibt es Kaltstart, Trockenlauf oder Mangelschmierung?",
    "Ist die Wellenoberfläche geeignet?",
    "Gibt es Einlaufspuren oder Drall?",
    "Ist die Montage sicher beherrschbar?",
    "Ist es ein Ersatzfall, ein Ausfall oder eine Neuauslegung?",
  ],
  strong: "Das Problem ist nicht nur fehlendes Wissen. Das Problem ist fehlende Struktur.",
  closing: "sealingAI bringt diese Struktur in den Dichtungsfall.",
};

export const nutzen = {
  id: "nutzen",
  headline: "sealingAI zeigt, was bekannt ist — und was noch fehlt.",
  text: [
    "Die Plattform trennt sauber zwischen bestätigten Angaben, geschätzten Angaben, fehlenden Angaben, kritischen Unsicherheiten und berechenbaren Kennwerten.",
    "So entsteht kein Bauchgefühl und keine schnelle Scheinsicherheit, sondern ein klarer technischer Bewertungsstand.",
    "Das hilft Anwendern, Herstellern und Entscheidern, schneller über denselben Fall zu sprechen.",
  ],
  states: [
    { label: "Bestätigt", tone: "success" as const },
    { label: "Geschätzt", tone: "warning" as const },
    { label: "Fehlt", tone: "muted" as const },
    { label: "Kritisch offen", tone: "danger" as const },
    { label: "Berechnet", tone: "navy" as const },
  ],
};

export const output = {
  id: "output",
  headline: "Aus einem Problem wird eine technische Grundlage.",
  intro: "Mit sealingAI erhalten Sie:",
  items: [
    "strukturierte Betriebsdaten",
    "Medien- und Temperaturerfassung",
    "Druck- und Bewegungsdaten",
    "Geometrie- und Einbauraumdaten",
    "erste technische Berechnungen",
    "Hinweise auf fehlende Angaben",
    "Risikopunkte",
    "Rückfragenplan",
    "Werkstoff- und Dichtungstyp-Orientierung",
    "vorbereitetes technisches Briefing",
  ],
  closing: ["Nicht als Freigabe.", "Nicht als Black Box.", "Sondern als nachvollziehbare Grundlage für den nächsten Schritt."],
  cta: "Kostenlosen Analysefall starten",
};

export const anwender = {
  id: "fuer-anwender",
  headline: "Schneller zur richtigen Frage. Besser vorbereitet zur Lösung.",
  intro:
    "Ob Konstruktion, Instandhaltung, Einkauf oder Qualität: sealingAI hilft, einen Dichtungsfall sauber zu erfassen, bevor falsche Entscheidungen oder unvollständige Anfragen entstehen.",
  cards: [
    {
      title: "Für Instandhaltung",
      text: "Wenn eine Dichtung ausfällt, zählt Zeit. sealingAI hilft, den Fall schnell zu ordnen: Anwendung, Schadensbild, Medium, Temperatur, Druck, Bewegung und offene Risiken.",
      nutzen: "schneller verstehen, was kritisch ist.",
    },
    {
      title: "Für Engineering",
      text: "Dichtungsauslegung ist kein einzelner Tabellenwert. sealingAI verbindet Werkstoff, Systembedingungen, Geometrie und Risiken zu einer strukturierten technischen Einordnung.",
      nutzen: "bessere Entscheidungsgrundlage vor der Auslegung.",
    },
    {
      title: "Für Einkauf",
      text: "Unvollständige Anfragen erzeugen Rückfragen, Verzögerungen und falsche Angebote. sealingAI erstellt eine saubere technische Anfragebasis.",
      nutzen: "bessere RFQs statt langer E-Mail-Schleifen.",
    },
    {
      title: "Für Qualität",
      text: "Schadensfälle brauchen Struktur. sealingAI dokumentiert bekannte Daten, offene Punkte und mögliche Einflussfaktoren nachvollziehbar.",
      nutzen: "klarere technische Kommunikation im Reklamations- oder Analyseprozess.",
    },
  ],
  cta: "Dichtungsfall kostenlos analysieren",
};

export const hersteller = {
  id: "fuer-hersteller",
  headline: "Weniger unklare Anfragen. Mehr qualifizierte RFQs.",
  intro: [
    "Hersteller erhalten oft Anfragen, die technisch kaum bewertbar sind:",
    "„Wir brauchen eine Dichtung für Öl, 80 °C. Bitte anbieten.“",
    "Das kostet Zeit. Vertrieb, Anwendungstechnik und Engineering müssen zuerst klären, was eigentlich gemeint ist.",
    "sealingAI bereitet Anfragen vor, bevor sie beim Hersteller landen.",
  ],
  briefingIntro: "Ein sealingAI-Briefing kann enthalten:",
  briefing: [
    "Anwendungskontext",
    "Medium",
    "Temperaturbereich",
    "Druckdaten",
    "Bewegung und Geschwindigkeit",
    "Geometrie",
    "Schadensbild",
    "offene Prüfpunkte",
    "gewünschte Menge",
    "technische Zielsetzung",
  ],
  strong: "Das senkt Klärungsaufwand und verbessert die Angebotsbasis.",
  closing: [
    "sealingAI verkauft Herstellern keine gekaufte technische Empfehlung.",
    "sealingAI bietet Zugang zu besser vorbereiteten technischen Anfragen.",
  ],
  cta: "Partnerprogramm anfragen",
};

export const unterschied = {
  id: "unterschied",
  headline: "Kein Katalogfilter. Kein Werbeportal. Kein Chatbot mit schöner Sprache.",
  compare: [
    "Kataloge zeigen Produkte.",
    "Suchmaschinen zeigen Treffer.",
    "Herstellerseiten zeigen das eigene Sortiment.",
    "Formulare sammeln Daten.",
  ],
  strong: "sealingAI prüft zuerst den technischen Fall.",
  questionsIntro: "Die Plattform fragt:",
  questions: [
    "Reichen die Angaben überhaupt?",
    "Was ist berechenbar?",
    "Was ist kritisch offen?",
    "Welche Randbedingungen fehlen?",
    "Was muss vor einer Herstelleranfrage geklärt werden?",
  ],
  closing: "Erst dadurch entsteht eine Anfrage, mit der Anwender und Hersteller wirklich arbeiten können.",
};

export const layerSection = {
  id: "schichten",
  headline: "Die Schichten hinter einer belastbaren Dichtungsentscheidung.",
  subline:
    "sealingAI macht sichtbar, welche Informationen bekannt sind, was berechenbar ist und welche Punkte vor einer belastbaren Bewertung fehlen.",
  layers: [
    { name: "Anwendungskontext", text: "Medium, Temperatur, Druck, Bewegung, Umgebung und Ziel der Anfrage." },
    { name: "Datenqualität", text: "Bestätigte Angaben, geschätzte Angaben, fehlende Angaben und kritische Unsicherheiten." },
    { name: "Berechnung", text: "Kennwerte wie Umfangsgeschwindigkeit, PV-relevante Größen und geometrische Plausibilität." },
    { name: "Werkstoff- und Dichtungstyp-Orientierung", text: "Materialklassen, Dichtungstypen, Einsatzgrenzen und Red Flags." },
    { name: "Erfahrungswissen", text: "Schadensbilder, typische Rückfragen, Montageeinflüsse und Herstellerfeedback." },
    { name: "Herstellerdialog", text: "Aus dem Fall entsteht eine strukturierte Anfragebasis für qualifizierte RFQs." },
  ],
};

export const guide = {
  id: "website-guide",
  headline: "Fragen zu sealingAI?",
  subline:
    "Der Website-Guide erklärt Ihnen, wie sealingAI funktioniert, warum die Plattform nützlich ist und wie Sie kostenlos starten oder Herstellerpartner werden.",
  placeholder: "Warum sollte ich sealingAI nutzen?",
  clarifier:
    "Der Website-Guide beantwortet Fragen zu sealingAI. Für konkrete technische Dichtungsfälle starten Sie bitte die kostenlose Analyse.",
  guardrail:
    "Ich kann Ihnen hier erklären, wie sealingAI funktioniert. Für eine technische Bewertung Ihres Dichtungsfalls starten Sie bitte die kostenlose Analyse. Dort werden Ihre Angaben strukturiert geprüft und offene Punkte sauber erfasst.",
};

/** FAQ shown visibly in the Website Guide AND used for the FAQPage JSON-LD. */
export const faqItems = [
  {
    question: "Warum sollte ich sealingAI nutzen?",
    answer:
      "sealingAI hilft Ihnen, einen Dichtungsfall sauber zu verstehen, bevor Sie auslegen, bestellen oder einen Hersteller anfragen. Die Plattform erkennt fehlende Angaben, berechnet erste Kennwerte und zeigt, welche Punkte für eine belastbare Bewertung noch offen sind. So starten Sie nicht mit einer unvollständigen E-Mail, sondern mit einem strukturierten technischen Fall.",
  },
  {
    question: "Was passiert nach dem kostenlosen Login?",
    answer:
      "Nach dem kostenlosen Login können Sie Ihren Dichtungsfall vollständig analysieren. Ihre Eingaben aus dem Vorcheck werden übernommen. sealingAI fragt gezielt nach fehlenden Angaben, strukturiert die Betriebsbedingungen und bereitet daraus eine technische Grundlage für die weitere Bewertung oder Herstelleranfrage vor.",
  },
  {
    question: "Ist sealingAI neutral?",
    answer:
      "Ja. Die technische Bewertung ist nicht käuflich. Hersteller können sich als Partner präsentieren, verifizieren lassen und qualifizierte Anfragen empfangen. Sie können aber keine technische Eignung kaufen. sealingAI trennt technische Bewertung und kommerzielle Partnerschaft klar voneinander.",
  },
  {
    question: "Wie hilft sealingAI Herstellern?",
    answer:
      "Hersteller erhalten häufig unvollständige Anfragen. sealingAI bereitet Dichtungsfälle vor, bevor sie beim Hersteller landen. Ein qualifiziertes Briefing enthält Anwendungskontext, Medium, Temperatur, Druck, Bewegung, Geometrie, Schadensbild und offene Prüfpunkte. Das reduziert Klärungsaufwand und verbessert die Angebotsbasis.",
  },
  {
    question: "Wie werde ich Herstellerpartner?",
    answer:
      "Hersteller können sealingAI-Partner werden, um sich professionell zu präsentieren und qualifizierte technische Anfragen zu empfangen. Der erste Schritt ist eine Partneranfrage. Danach werden Unternehmensdaten, Ansprechpartner und technische Kompetenzen geprüft.",
  },
];

export const experienceLayer = {
  id: "erfahrung",
  headline: "Erfahrung, die nicht verloren geht.",
  text: [
    "Dichtungstechnik lebt von Erfahrung.",
    "Viele wichtige Erkenntnisse stehen nicht sauber in Datenblättern. Sie stecken in alten Projekten, Schadensfällen, E-Mails, Excel-Listen, Herstellerhinweisen und im Kopf erfahrener Fachleute.",
    "sealingAI macht diese Erfahrung Schritt für Schritt nutzbar.",
    "Langfristig entsteht eine strukturierte Erfahrungsbasis der Dichtungstechnik:",
  ],
  items: [
    "typische Schadensbilder",
    "bewährte Lösungswege",
    "kritische Betriebsbedingungen",
    "häufig fehlende Parameter",
    "Werkstoff- und Medienerfahrungen",
    "Montagehinweise",
    "Herstellerfeedback",
    "gelöste Fälle",
  ],
  strong: "Aus einzelnen Erfahrungen wird reproduzierbare Sealing Intelligence.",
};

export const soFunktioniert = {
  id: "so-funktioniert",
  headline: "Vom Dichtungsproblem zur qualifizierten Anfrage.",
  steps: [
    { title: "Fall beschreiben", text: "Sie geben ein, was bekannt ist: Medium, Temperatur, Druck, Bewegung, Abmessungen, Schadensbild oder Ziel." },
    { title: "Lücken erkennen", text: "sealingAI erkennt, welche Angaben fehlen und welche davon technisch kritisch sind." },
    { title: "Kennwerte berechnen", text: "Wo möglich, berechnet sealingAI erste technische Werte, zum Beispiel Umfangsgeschwindigkeit oder PV-relevante Größen." },
    { title: "Risiken sichtbar machen", text: "Das System zeigt, welche Punkte vor einer belastbaren Bewertung geklärt werden sollten." },
    { title: "Briefing vorbereiten", text: "Aus dem Fall entsteht eine strukturierte technische Grundlage für Auslegung, Beschaffung oder Herstelleranfrage." },
    { title: "Anfrage einreichen", text: "Auf Wunsch kann der Fall über sealingAI als qualifizierte Anfrage weitergeführt werden." },
  ],
  cta: "Jetzt kostenlos starten",
};

export const vertrauen = {
  id: "neutralitaet",
  headline: "Technische Neutralität ist nicht käuflich.",
  text: [
    "sealingAI trennt technische Bewertung und kommerzielle Partnerschaft klar voneinander.",
    "Hersteller können sich präsentieren, verifizieren lassen und qualifizierte Anfragen empfangen.",
    "Aber:",
  ],
  strong: "Kein Hersteller kann technische Eignung kaufen.",
  detail:
    "Die Bewertung eines Dichtungsfalls basiert auf Anwendung, Datenlage, Risiken, Werkstoffwissen, Erfahrung und nachvollziehbarer Prüfung.",
  closing: "Das ist der Unterschied zwischen Werbung und technischer Plattform.",
};

export const branchenplattform = {
  id: "branchenplattform",
  headline: "Die Dichtungstechnik an einem Ort.",
  intro: "sealingAI baut eine unabhängige Plattform für Dichtungstechnik auf:",
  items: ["Wissen", "Werkstoffe", "Medien", "Anwendungen", "Dichtungstypen", "Erfahrungswerte", "Herstellerkompetenzen", "technische Anfragen"],
  tiers: [
    { name: "Gelistet", text: "Gelistete Unternehmen sind nicht automatisch Partner." },
    { name: "Verified Partner", text: "Verified Partner sind geprüft." },
    { name: "RFQ Partner", text: "RFQ Partner können qualifizierte Anfragen empfangen." },
    { name: "Expert Partner", text: "Expert Partner können zusätzlich Produkte, Datenblätter und Fachinhalte präsentieren." },
  ],
  closing: "So entsteht Transparenz für Anwender und ein hochwertiger Zugang für Hersteller.",
};

export const finalCta = {
  id: "start",
  headline: "Starten Sie mit Ihrem Dichtungsfall.",
  text: "Geben Sie ein, was Sie wissen. sealingAI zeigt Ihnen, was berechenbar ist, was fehlt und welcher nächste Schritt sinnvoll ist.",
  button: "Kostenlos analysieren",
  smallLine: "Der Vorcheck ist kostenlos. Für die vollständige Analyse erstellen Sie ein kostenloses Konto.",
  manufacturer: {
    headline: "Sie sind Hersteller oder Händler?",
    text: "Werden Sie sealingAI-Partner und erhalten Sie Zugang zu besser vorbereiteten technischen Anfragen aus der Dichtungstechnik.",
    button: "Partnerprogramm anfragen",
  },
};

/** Footer columns. Legal links are kept even where the page does not exist yet
 * (TODO: create Impressum/Datenschutz/Nutzungsbedingungen + /kontakt) — never
 * broken. Non-existent product routes point to on-page anchors, not thin pages. */
export const footerColumns = [
  {
    title: "Plattform",
    links: [
      { label: "So funktioniert sealingAI", href: "/#so-funktioniert" },
      { label: "Kostenlos analysieren", href: ANALYZE_HREF },
      { label: "Fragen zu sealingAI", href: "/#website-guide" },
      { label: "Sicherheit & Neutralität", href: "/#neutralitaet" },
    ],
  },
  {
    title: "Für Anwender",
    links: [
      { label: "Konstruktion", href: "/#fuer-anwender" },
      { label: "Instandhaltung", href: "/#fuer-anwender" },
      { label: "Einkauf", href: "/#fuer-anwender" },
      { label: "Qualität", href: "/#fuer-anwender" },
    ],
  },
  {
    title: "Für Hersteller",
    links: [
      { label: "Herstellerpartner werden", href: PARTNER_HREF },
      { label: "Qualifizierte RFQs", href: "/#fuer-hersteller" },
      { label: "Verified Partner", href: "/#branchenplattform" },
      { label: "Partnerprogramm", href: PARTNER_HREF },
    ],
  },
  {
    title: "Wissen",
    links: [
      { label: "Dichtungstechnik", href: "/wissen" },
      { label: "Dichtungstypen", href: "/wissen" },
      { label: "Werkstoffe", href: "/werkstoffe" },
      { label: "Schadensanalyse", href: "/wissen" },
    ],
  },
  {
    title: "Dichtungstypen",
    links: [
      { label: "RWDR", href: "/wissen" },
      { label: "O-Ring", href: "/wissen" },
      { label: "Hydraulikdichtung", href: "/wissen" },
      { label: "PTFE-Dichtung", href: "/werkstoffe" },
    ],
  },
  {
    title: "Rechtliches",
    links: [
      { label: "Impressum", href: "/impressum" },
      { label: "Datenschutz", href: "/datenschutz" },
      { label: "Nutzungsbedingungen", href: "/nutzungsbedingungen" },
      { label: "Auftragsverarbeitung (AVV)", href: "/auftragsverarbeitung" },
    ],
  },
];
