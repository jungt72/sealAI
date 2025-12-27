import { LandingPageData } from './types';

export const mockData: LandingPageData = {
    global: {
        id: 1,
        siteName: 'SealAI',
        navbar: {
            id: 1,
            brand_name: 'SEALAI',
            items: [],
            show_search: true,
            show_menu: true,
        },
        navbarLinks: [],
        footerColumns: [],
        footerBottomLinks: [],
        copyrightText: '© 2024 SealAI. All rights reserved.',
        sectionNavItems: [],
    },
    homepage: {
        hero: {
            id: 1,
            title: "Pioneering sustainable AI for a safe and united world",
            subtitle: "",
            cta_text: "Get Started",
            cta_link: "/signup",
            background_image: {
                id: 1,
                url: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop",
                alternativeText: "Hero Background",
                width: 1920,
                height: 1080,
            },
        },
        introHeadline: "SealAI revolutioniert die Dichtungstechnik mit KI-gestützter Beratung und präzisen Empfehlungen.",
        productTabs: [
            {
                id: 1,
                title: "Power Apps",
                accordionItems: [
                    {
                        id: 1,
                        title: "Erstellen Sie Apps mit natuerlicher Sprache",
                        description: "Beschreiben Sie einfach, was Sie brauchen, und Copilot erstellt die App fuer Sie.",
                        link: "#"
                    },
                    {
                        id: 2,
                        title: "Optimieren Sie Ihre Workflows",
                        description: "Automatisieren Sie repetitive Aufgaben und sparen Sie wertvolle Zeit.",
                        link: "#"
                    },
                    {
                        id: 3,
                        title: "Integrieren Sie Ihre Daten",
                        description: "Verbinden Sie verschiedene Datenquellen nahtlos miteinander.",
                        link: "#"
                    }
                ],
                image: {
                    id: 10,
                    url: "https://images.unsplash.com/photo-1551434678-e076c223a692?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Power Apps Interface",
                    width: 800,
                    height: 600
                }
            },
            {
                id: 2,
                title: "Power Automate",
                accordionItems: [
                    {
                        id: 4,
                        title: "Automatisieren Sie Geschaeftsprozesse",
                        description: "Erstellen Sie Flows, die Ihre Prozesse rationalisieren.",
                        link: "#"
                    },
                    {
                        id: 5,
                        title: "KI-gestuetzte Automatisierung",
                        description: "Nutzen Sie KI, um intelligente Workflows zu erstellen.",
                        link: "#"
                    }
                ],
                image: {
                    id: 11,
                    url: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Power Automate Dashboard",
                    width: 800,
                    height: 600
                }
            },
            {
                id: 3,
                title: "Power BI",
                accordionItems: [
                    {
                        id: 6,
                        title: "Visualisieren Sie Ihre Daten",
                        description: "Erstellen Sie aussagekraeftige Dashboards und Berichte.",
                        link: "#"
                    },
                    {
                        id: 7,
                        title: "Treffen Sie datenbasierte Entscheidungen",
                        description: "Nutzen Sie Echtzeit-Analysen fuer bessere Geschaeftsentscheidungen.",
                        link: "#"
                    }
                ],
                image: {
                    id: 12,
                    url: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Power BI Analytics",
                    width: 800,
                    height: 600
                }
            }
        ],
        contentSections: [
            {
                id: 1,
                title: "Transformieren, wie Ihr Unternehmen arbeitet und Loesungen erstellt",
                subtitle: "Ermoeglichen Sie Ihren Mitarbeitern, Innovationen voranzutreiben, indem Sie ihnen die Tools an die Hand geben, die sie benoetigen, um komplexe Probleme zu loesen.",
                image: {
                    id: 2,
                    url: "https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Team working together",
                    width: 800,
                    height: 600,
                },
                image_position: 'left',
                background_color: 'white',
            },
        ],
        features: [
            {
                id: 1,
                title: "Optimieren von Workflows mit KI-gestuetzten Low-Code-Automatisierungstools",
                description: "Erstellen Sie Flows, die Ihre Prozesse rationalisieren und Zeit sparen.",
                icon: "Zap",
            },
            {
                id: 2,
                title: "Identifizieren von Ineffizienzen in vorhandenen Prozessen",
                description: "Nutzen Sie Process Mining, um Engpaesse zu finden und zu beheben.",
                icon: "Search",
            },
            {
                id: 3,
                title: "Automatisieren von Aufgaben mit einem Show-and-Tell-Ansatz",
                description: "Zeigen Sie dem Copilot, was zu tun ist, und lassen Sie ihn die Arbeit erledigen.",
                icon: "Bot",
            },
            {
                id: 4,
                title: "Erstellen von Apps durch natuerliche Sprache",
                description: "Beschreiben Sie einfach, was Sie brauchen, und SealAI erstellt die App fuer Sie.",
                icon: "MessageSquare",
            },
        ],
        community: {
            id: 1,
            title: "SealAI Community Conference",
            description: "Lernen Sie von Experten, vernetzen Sie sich mit Gleichgesinnten und entdecken Sie die neuesten Innovationen.",
            cta_text: "Mehr erfahren",
            cta_link: "#",
            image: {
                id: 3,
                url: "https://images.unsplash.com/photo-1515187029135-18ee286d815b?auto=format&fit=crop&w=800&q=80",
                alternativeText: "Conference audience",
                width: 800,
                height: 600,
            },
        },
        nextSteps: [
            {
                id: 1,
                title: "Platform-Produkte testen",
                description: "Probieren Sie SealAI kostenlos aus und erleben Sie die Power von Low-Code.",
                cta_text: "Jetzt testen",
                cta_link: "#",
                image: {
                    id: 4,
                    url: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Analytics dashboard",
                    width: 800,
                    height: 600,
                },
            },
            {
                id: 2,
                title: "An den Vertrieb wenden",
                description: "Sprechen Sie mit einem Experten darueber, wie SealAI Ihrem Unternehmen helfen kann.",
                cta_text: "Kontakt aufnehmen",
                cta_link: "#",
                image: {
                    id: 5,
                    url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=800&q=80",
                    alternativeText: "Business meeting",
                    width: 800,
                    height: 600,
                },
            },
        ],
    }
};
