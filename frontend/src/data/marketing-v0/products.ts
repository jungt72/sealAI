import type { Product } from "@/types/marketing-v0/products";

export const products: Product[] = [
    {
        id: "parameters",
        name: "Einsatzparameter erfassen",
        image: "/images/sealai-parameters.jpg",
        features: [
            {
                title: "Relevante Einsatzbedingungen strukturiert erfassen",
                description:
                    "SealAI führt alle entscheidungsrelevanten Parameter wie Temperatur, Druck, Medium, Drehzahl und Einbausituation in einem konsistenten technischen Zustand zusammen.",
                link: "Mehr erfahren",
            },
            {
                title: "Unvollständige oder widersprüchliche Angaben erkennen",
                description:
                    "Fehlende, unplausible oder widersprüchliche Parameter werden transparent gemacht, bevor sie zu Fehlentscheidungen führen.",
                link: "Mehr erfahren",
            },
            {
                title: "Gemeinsame Grundlage für alle Entscheidungen schaffen",
                description:
                    "Alle weiteren Bewertungen und Empfehlungen basieren auf demselben aktuellen Parameterzustand – nachvollziehbar und reproduzierbar.",
                link: "Mehr erfahren",
            },
        ],
    },
    {
        id: "evaluation",
        name: "Technische Bewertung",
        image: "/images/sealai-evaluation.jpg",
        features: [
            {
                title: "Materialien und Bauformen technisch bewerten",
                description:
                    "SealAI prüft Materialien und Dichtungskonzepte anhand definierter Einsatzgrenzen, Medienverträglichkeiten und temperatur- bzw. drehzahlabhängiger Einschränkungen.",
                link: "Mehr erfahren",
            },
            {
                title: "Ungeeignete Lösungen konsequent ausschließen",
                description:
                    "Technisch riskante oder ungeeignete Optionen werden frühzeitig ausgeschlossen – inklusive nachvollziehbarer Begründung.",
                link: "Mehr erfahren",
            },
            {
                title: "Bewertungen transparent dokumentieren",
                description:
                    "Jede technische Bewertung ist erklärbar und kann intern oder extern nachvollzogen werden.",
                link: "Mehr erfahren",
            },
        ],
    },
    {
        id: "comparison",
        name: "Lösungen vergleichen",
        image: "/images/sealai-comparison.jpg",
        features: [
            {
                title: "Geeignete Dichtungen strukturiert gegenüberstellen",
                description:
                    "Mehrere technisch geeignete Lösungen werden anhand relevanter Kriterien wie Einsatzgrenzen, Robustheit und Randbedingungen verglichen.",
                link: "Mehr erfahren",
            },
            {
                title: "Vor- und Nachteile klar herausarbeiten",
                description:
                    "SealAI zeigt auf, welche Kompromisse einzelne Lösungen mit sich bringen und in welchem Einsatzfall sie sinnvoll sind.",
                link: "Mehr erfahren",
            },
            {
                title: "Entscheidungen absichern statt raten",
                description:
                    "Der Vergleich dient nicht der Produktauswahl nach Bauchgefühl, sondern der fundierten technischen Abwägung.",
                link: "Mehr erfahren",
            },
        ],
    },
    {
        id: "recommendation",
        name: "Begründete Empfehlung",
        image: "/images/sealai-recommendation.jpg",
        features: [
            {
                title: "Technisch belastbare Empfehlungen erhalten",
                description:
                    "Auf Basis aller Bewertungen empfiehlt SealAI geeignete Dichtungen für den konkreten Einsatzfall.",
                link: "Mehr erfahren",
            },
            {
                title: "Empfehlungen nachvollziehbar begründen",
                description:
                    "Jede Empfehlung ist technisch erklärbar – inklusive Ausschlussgründen für Alternativen.",
                link: "Mehr erfahren",
            },
            {
                title: "Grundlage für Freigaben und Dokumentation schaffen",
                description:
                    "Empfehlungen können direkt für interne Freigaben, Kundenabstimmungen oder QS-Dokumentationen genutzt werden.",
                link: "Mehr erfahren",
            },
        ],
    },
    {
        id: "neutrality",
        name: "Neutral & herstellerunabhängig",
        image: "/images/sealai-neutrality.jpg",
        features: [
            {
                title: "Keine gekauften Empfehlungen",
                description:
                    "SealAI priorisiert keine Produkte aus kommerziellen Gründen. Empfehlungen basieren ausschließlich auf technischer Eignung.",
                link: "Mehr erfahren",
            },
            {
                title: "Kostenlos für Anwender",
                description:
                    "Konstrukteure und Anwendungstechniker nutzen SealAI ohne Lizenzkosten oder Paywalls.",
                link: "Mehr erfahren",
            },
            {
                title: "Klare Trennung von Entscheidung und Vermarktung",
                description:
                    "Herstellerdaten fließen strukturiert ein, ohne die Entscheidungslogik zu beeinflussen.",
                link: "Mehr erfahren",
            },
        ],
    },
];
