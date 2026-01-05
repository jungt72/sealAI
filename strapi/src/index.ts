import type { Core } from '@strapi/strapi';

export default {
    /**
     * An asynchronous register function that runs before
     * your application is initialized.
     *
     * This gives you an opportunity to extend code.
     */
    register({ strapi }: { strapi: Core.Strapi }) { },

    /**
     * An asynchronous bootstrap function that runs before
     * your application gets started.
     *
     * This gives you an opportunity to set up your data model,
     * run jobs, or perform some special logic.
     */
    async bootstrap({ strapi }: { strapi: Core.Strapi }) {
        try {
            console.log('Starting Bootstrap...');

            // DEBUG: Log Content Types
            const contentTypes = Object.keys(strapi.contentTypes).filter(key => key.startsWith('api::'));
            console.log('DEBUG: Loaded API Content Types:', contentTypes);

            // Set Public Permissions
            // @ts-ignore
            const publicRole = await strapi.db.query('plugin::users-permissions.role').findOne({ where: { type: 'public' } });

            if (publicRole) {
                const permissionsToEnable = [
                    'api::hero.hero.find',
                    'api::hero.hero.findOne',
                    'api::section.section.find',
                    'api::section.section.findOne',
                    'api::feature.feature.find',
                    'api::feature.feature.findOne',
                    'api::next-step.next-step.find',
                    'api::next-step.next-step.findOne',
                    'api::community-conference.community-conference.find',
                    'api::community-conference.community-conference.findOne',
                    'api::global.global.find',
                    'api::global.global.findOne',
                    'api::product-tab.product-tab.find',
                    'api::product-tab.product-tab.findOne',
                ];

                for (const action of permissionsToEnable) {
                    // @ts-ignore
                    const existing = await strapi.db.query('plugin::users-permissions.permission').findOne({
                        where: {
                            role: publicRole.id,
                            action: action
                        }
                    });

                    if (existing) {
                        if (!existing.enabled) {
                            // @ts-ignore
                            await strapi.db.query('plugin::users-permissions.permission').update({
                                where: { id: existing.id },
                                data: { enabled: true },
                            });
                            console.log(`Enabled existing permission: ${action}`);
                        }
                    } else {
                        // @ts-ignore
                        await strapi.db.query('plugin::users-permissions.permission').create({
                            data: {
                                action: action,
                                role: publicRole.id,
                                enabled: true
                            }
                        });
                        console.log(`Created and enabled permission: ${action}`);
                    }
                }
            }

            // --- Populate initial content ---

            // Create Hero
            // @ts-ignore
            let hero = await strapi.db.query('api::hero.hero').findOne({});
            if (!hero) {
                // @ts-ignore
                await strapi.entityService.create('api::hero.hero', {
                    data: {
                        title: 'Pioneering sustainable AI for a safe and united world',
                        subtitle: '',
                        cta_text: 'Learn more',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                });
                console.log('Hero content created');
            } else {
                // @ts-ignore
                await strapi.entityService.update('api::hero.hero', hero.id, {
                    data: { publishedAt: new Date() }
                });
            }

            // Create Sections
            // @ts-ignore
            const sectionsExist = await strapi.db.query('api::section.section').findMany({});
            if (sectionsExist.length === 0) {
                const sections = [
                    {
                        title: 'Transformieren, wie Ihr Unternehmen arbeitet und Lösungen erstellt',
                        subtitle: 'Ermöglichen Sie Ihren Mitarbeitern, Innovationen voranzutreiben, indem Sie ihnen die Tools an die Hand geben, die sie benötigen, um komplexe Probleme zu lösen.',
                        image_position: 'left',
                        background_color: 'white',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Intuitiveres Arbeiten',
                        subtitle: 'Mit Copilot in Microsoft Power Platform können Sie Geschäftsprozesse ganz einfach optimieren und automatisierte Workflows erstellen.',
                        image_position: 'right',
                        background_color: 'light-blue',
                        publishedAt: new Date(),
                    },
                ];

                for (const section of sections) {
                    // @ts-ignore
                    await strapi.entityService.create('api::section.section', { data: section });
                }
                console.log('Section content created');
            }

            // Create Features
            // @ts-ignore
            const featuresExist = await strapi.db.query('api::feature.feature').findMany({});
            if (featuresExist.length === 0) {
                const features = [
                    {
                        title: 'Sprache in Code umwandeln',
                        icon: 'Code',
                        description: 'Erstellen Sie Apps für Webanwendungen oder mobile Geräte mit natürlicher Sprache.',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Chatbots erstellen',
                        icon: 'MessageSquare',
                        description: 'Erstellen Sie Chatbots mit generativer KI und großen Sprachmodellen.',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Daten automatisieren',
                        icon: 'Database',
                        description: 'Nutzen Sie KI, um sich wiederholende Aufgaben zu automatisieren und Zeit zu sparen.',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Workflowanalysen',
                        icon: 'TrendingUp',
                        description: 'Analysieren Sie Ihre Geschäftsprozesse mit detaillierten Einblicken.',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Cloud-Integration',
                        icon: 'Cloud',
                        description: 'Nahtlose Integration mit Azure und anderen Cloud-Diensten.',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Sicherheit',
                        icon: 'Shield',
                        description: 'Enterprise-Level-Sicherheit für Ihre Daten und Anwendungen.',
                        publishedAt: new Date(),
                    },
                ];

                for (const feature of features) {
                    // @ts-ignore
                    await strapi.entityService.create('api::feature.feature', { data: feature });
                }
                console.log('Feature content created');
            }

            // Create Next Steps
            // @ts-ignore
            const nextStepsExist = await strapi.db.query('api::next-step.next-step').findMany({});
            if (nextStepsExist.length === 0) {
                const nextSteps = [
                    {
                        title: 'Erste Schritte',
                        description: 'Lernen Sie die Grundlagen von Power Platform kennen.',
                        cta_text: 'Jetzt beginnen',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Schulungen',
                        description: 'Vertiefen Sie Ihr Wissen mit unseren Schulungsmaterialien.',
                        cta_text: 'Mehr erfahren',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Community',
                        description: 'Werden Sie Teil unserer wachsenden Community.',
                        cta_text: 'Beitreten',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                ];

                for (const step of nextSteps) {
                    // @ts-ignore
                    await strapi.entityService.create('api::next-step.next-step', { data: step });
                }
                console.log('Next Step content created');
            }

            // Create Community Conference
            // @ts-ignore
            const communityExists = await strapi.db.query('api::community-conference.community-conference').findOne({});
            if (!communityExists) {
                // @ts-ignore
                await strapi.entityService.create('api::community-conference.community-conference', {
                    data: {
                        title: 'JOIN.THE.DOTS',
                        description: 'Treffen Sie Experten, lernen Sie neue Technologien kennen und vernetzen Sie sich mit Gleichgesinnten.',
                        cta_text: 'Jetzt anmelden',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                });
                console.log('Community Conference content created');
            }

            // Create Global
            // @ts-ignore
            const globalExists = await strapi.db.query('api::global.global').findOne({});
            if (!globalExists) {
                // @ts-ignore
                await strapi.entityService.create('api::global.global', {
                    data: {
                        siteName: 'SealAI',
                        copyrightText: '© 2025 SealAI GmbH. Alle Rechte vorbehalten.',
                        navbarLinks: [
                            { label: 'Careers', href: '#', isExternal: false },
                            { label: 'Investors', href: '#', isExternal: false },
                            { label: 'Suppliers', href: '#', isExternal: false },
                            { label: 'Newsroom', href: '#', isExternal: false }
                        ],
                        sectionNavItems: [
                            { label: 'Produkte', href: 'products', isExternal: false },
                            { label: 'Features', href: 'features', isExternal: false },
                            { label: 'Community', href: 'community', isExternal: false },
                            { label: 'Nächste Schritte', href: 'next-steps', isExternal: false }
                        ],
                        footerColumns: [
                            {
                                title: 'Neuigkeiten',
                                links: [
                                    { label: 'Features', href: '#', isExternal: false },
                                    { label: 'Sicherheit', href: '#', isExternal: false },
                                    { label: 'Roadmap', href: '#', isExternal: false }
                                ]
                            },
                            {
                                title: 'Microsoft Store',
                                links: [
                                    { label: 'Konto-Profil', href: '#', isExternal: false },
                                    { label: 'Download Center', href: '#', isExternal: false },
                                    { label: 'Rückgaben', href: '#', isExternal: false }
                                ]
                            },
                            {
                                title: 'Bildungswesen',
                                links: [
                                    { label: 'Microsoft Bildung', href: '#', isExternal: false },
                                    { label: 'Geräte für Bildung', href: '#', isExternal: false },
                                    { label: 'Microsoft Teams', href: '#', isExternal: false }
                                ]
                            },
                            {
                                title: 'Unternehmen',
                                links: [
                                    { label: 'Microsoft Cloud', href: '#', isExternal: false },
                                    { label: 'Microsoft Security', href: '#', isExternal: false },
                                    { label: 'Azure', href: '#', isExternal: false }
                                ]
                            }
                        ],
                        footerBottomLinks: [
                            { label: 'Impressum', href: '#', isExternal: false },
                            { label: 'Datenschutz', href: '#', isExternal: false },
                            { label: 'Cookies', href: '#', isExternal: false }
                        ],
                        publishedAt: new Date(),
                    },
                });
                console.log('Global content created');
            }

            // Create Product Tabs
            // @ts-ignore
            const productTabsExist = await strapi.db.query('api::product-tab.product-tab').findMany({});
            if (productTabsExist.length === 0) {
                const productTabs = [
                    {
                        title: 'Copilot in Power Automate',
                        order: 1,
                        accordionItems: [
                            {
                                title: 'Optimieren von Workflows mit KI-gestützten Low-Code-Automatisierungstools',
                                description: 'Optimieren Sie Geschäftsprozesse ganz einfach und erstellen Sie automatisierte Workflows, indem Sie die Ziele in ihren eigenen Worten beschreiben.',
                                link: '#'
                            },
                            {
                                title: 'Identifizieren von Ineffizienzen in vorhandenen Prozessen',
                                description: 'Nutzen Sie Process Mining, um Engpässe zu finden und zu beheben.',
                                link: '#'
                            },
                            {
                                title: 'Automatisieren von Aufgaben mit einem „Show-and-Tell“ - Ansatz',
                                description: 'Zeigen Sie dem Copilot, was zu tun ist, und lassen Sie ihn die Arbeit erledigen.',
                                link: '#'
                            }
                        ],
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Copilot in Power Apps',
                        order: 2,
                        accordionItems: [
                            {
                                title: 'Erstellen von Apps durch natürliche Sprache',
                                description: 'Beschreiben Sie einfach, was Sie brauchen, und SealAI erstellt die App für Sie.',
                                link: '#'
                            }
                        ],
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Copilot in Microsoft Fabric',
                        order: 3,
                        accordionItems: [
                            {
                                title: 'Datenanalyse vereinfachen',
                                description: 'Analysieren Sie große Datenmengen mit KI-Unterstützung.',
                                link: '#'
                            }
                        ],
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Copilot in Power Pages',
                        order: 4,
                        accordionItems: [
                            {
                                title: 'Websites erstellen mit KI',
                                description: 'Erstellen Sie professionelle Websites im Handumdrehen.',
                                link: '#'
                            }
                        ],
                        publishedAt: new Date(),
                    },
                    {
                        title: 'Microsoft Copilot Studio',
                        order: 5,
                        accordionItems: [
                            {
                                title: 'Chatbots erstellen',
                                description: 'Entwickeln Sie intelligente Chatbots ohne Code.',
                                link: '#'
                            }
                        ],
                        publishedAt: new Date(),
                    }
                ];

                for (const tab of productTabs) {
                    // @ts-ignore
                    await strapi.entityService.create('api::product-tab.product-tab', { data: tab });
                }
                console.log('Product Tabs content created');
            }

            console.log('Bootstrap completed successfully!');
        } catch (error) {
            console.error('Error in bootstrap:', error);
        }
    },
};
