/**
 * sealingAI homepage content — single source of truth for the marketing copy.
 * Keeping the German copy here keeps the page component structural.
 *
 * No claims of final release, guaranteed suitability, or manufacturer approval.
 * Allowed wording stays scoped: screening, orientation, review required
 * (see AGENTS.md § Safety Boundaries).
 */

/** Analysis handoff: the auth-gated analysis workspace (served by frontend-v2). */
export const ANALYZE_HREF = "/dashboard/new";
/**
 * Registration / account entry point. There is currently no dedicated signup
 * route — /login triggers the Keycloak auth flow for both sign-in and account
 * creation, and /dashboard/new is gated behind the same flow for anonymous
 * visitors. Kept as its own export so header/CTA call sites read intent-first.
 */
export const REGISTER_HREF = ANALYZE_HREF;
/** Manufacturer partner enquiry. TODO(frontend): replace with a dedicated /partner route/form. */
export const PARTNER_HREF = "/kontakt";
export const TEASER_STORAGE_KEY = "sealingai.homepageTeaserState";

export const heroContent = {
  headline: "Sealing Intelligence für Dichtungstechnik",
  subline:
    "Die zentrale Anlaufstelle für Wissen, Bewertung und Orientierung in der industriellen Dichtungstechnik.",
  cta: "sealingAI entdecken",
};

export const highlights = {
  id: "highlights",
  headline: "Sealing Intelligence Highlights",
  intro:
    "Einblicke in Wissen, Bewertung und Orientierung für die industrielle Dichtungstechnik. Klar, strukturiert und nachvollziehbar.",
  cards: [
    {
      key: "wissenshub",
      title: "Wissenshub",
      text: "Fachinformationen, Normen, Werkstoffe und Praxiswissen an einem Ort.",
    },
    {
      key: "materialvergleich",
      title: "Materialvergleich",
      text: "Dichtungswerkstoffe objektiv vergleichen und technische Zielkonflikte erkennen.",
    },
    {
      key: "dichtungssituation",
      title: "Dichtungssituation",
      text: "Betriebsdaten, Medien, Temperaturen und Risiken strukturiert bewerten.",
    },
    {
      key: "hersteller-fit",
      title: "Hersteller-Fit",
      text: "Passende Kompetenzen, Produkte und Ansprechpartner finden.",
    },
  ],
};

export const teamUseCases = {
  id: "team",
  headlineLines: ["Für jedes Team.", "Jede Aufgabe."],
  subline:
    "sealingAI unterstützt alle Bereiche entlang des Dichtungsprozesses — vom ersten Verständnis bis zur besseren Entscheidung.",
  cards: [
    { key: "engineering", title: "Engineering", text: "Technische Zusammenhänge schneller einordnen." },
    { key: "einkauf", title: "Einkauf", text: "Anfragen klarer und vollständiger vorbereiten." },
    { key: "instandhaltung", title: "Instandhaltung", text: "Schadensfälle strukturiert erfassen." },
    { key: "hersteller", title: "Hersteller", text: "Qualifizierte Anfragen empfangen." },
    { key: "vertrieb", title: "Vertrieb / Technische Beratung", text: "Kundenanfragen fundiert begleiten." },
    { key: "qualitaet", title: "Qualitätsmanagement", text: "Bewertungen nachvollziehbar dokumentieren." },
  ],
};

export const sealingIntelligence = {
  id: "intelligence",
  headline: "Introducing Sealing Intelligence",
  subline:
    "Ein intelligenter Arbeitsraum, der Dichtungswissen, Anwendungskontext und Herstellerkompetenz verbindet.",
  modules: [
    { key: "fachwissen", title: "Fachwissen", text: "Normen, Werkstoffe und Praxiswissen strukturiert verfügbar." },
    { key: "materialdaten", title: "Materialdaten", text: "Werkstoffeigenschaften objektiv vergleichbar." },
    { key: "anwendungsdaten", title: "Anwendungsdaten", text: "Medien, Temperaturen und Betriebsbedingungen erfasst." },
    { key: "situation", title: "Dichtungssituation", text: "Der technische Fall strukturiert zusammengeführt." },
    { key: "bewertung", title: "Bewertung & Rückfragen", text: "Offene Punkte klar benannt, nicht verschwiegen." },
    { key: "herstellerkompetenz", title: "Herstellerkompetenz", text: "Passende Hersteller sichtbar gemacht." },
    { key: "dokumentation", title: "Dokumentation & nächste Schritte", text: "Ergebnisse nachvollziehbar festgehalten." },
    { key: "sicherheit", title: "Sicherheit & Neutralität", text: "Unabhängige, quellenbasierte Orientierung." },
  ],
  demo: {
    eyebrow: "Live-Demonstration",
    headline: "Dichtungssituation vorprüfen",
    subline: "Ein Baustein von Sealing Intelligence — als Screening, nicht als Freigabe.",
  },
};

export const trustNeutrality = {
  id: "neutralitaet",
  headline: "Technische Orientierung, nicht gekaufte Empfehlung.",
  text: "sealingAI kann Hersteller sichtbar machen. Die technische Bewertung bleibt unabhängig, nachvollziehbar und quellenbasiert.",
  points: [
    "Quellen und Annahmen sichtbar",
    "Unsicherheiten klar benannt",
    "Hersteller-Fit transparent",
    "Keine gekaufte technische Bewertung",
    "Mensch bleibt verantwortlich",
  ],
};

export const finalCta = {
  id: "start",
  headline: "Dichtungstechnik. Verstanden.",
  subline:
    "Entdecken Sie sealingAI als zentrale Anlaufstelle für Wissen, Bewertung und Orientierung in der industriellen Dichtungstechnik.",
  primaryCta: "Registrieren",
  secondaryCta: "Für Hersteller",
};

/**
 * Website Guide content (FAQ chips + guardrail copy). Not rendered on the
 * current homepage IA (no visible FAQ section) — kept only because
 * `WebsiteGuide.tsx` and its test still import these and remain a valid,
 * independently tested standalone component. Retire both together if the
 * component is ever fully removed.
 */
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

/** See `guide` doc comment above — same retirement note applies. */
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

/** Footer columns. `/impressum` is kept linked even though the page 404s today —
 * it needs real Handelsregister/Geschäftsführer/USt-ID data (docs/seo/baseline.md),
 * not a broken-link fix. Non-existent product routes point to on-page anchors,
 * not thin pages. */
export const footerColumns = [
  {
    title: "Plattform",
    links: [
      { label: "Sealing Intelligence", href: "/#intelligence" },
      { label: "Registrieren", href: REGISTER_HREF },
      { label: "Highlights", href: "/#highlights" },
      { label: "Sicherheit & Neutralität", href: "/#neutralitaet" },
    ],
  },
  {
    title: "Für Teams",
    links: [
      { label: "Engineering", href: "/#team" },
      { label: "Instandhaltung", href: "/#team" },
      { label: "Einkauf", href: "/#team" },
      { label: "Qualitätsmanagement", href: "/#team" },
    ],
  },
  {
    title: "Für Hersteller",
    links: [
      { label: "Herstellerpartner werden", href: PARTNER_HREF },
      { label: "Hersteller-Fit", href: "/#highlights" },
      { label: "Qualifizierte Anfragen", href: "/#team" },
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
      { label: "Methodik", href: "/methodik" },
      { label: "Quellen & Prüfstatus", href: "/quellen" },
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
