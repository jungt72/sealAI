module.exports = async () => {
    // Set permissions for public role
    const publicRole = await strapi
        .query('plugin::users-permissions.role')
        .findOne({ where: { type: 'public' } });

    if (publicRole) {
        const permissions = await strapi
            .query('plugin::users-permissions.permission')
            .findMany({
                where: {
                    role: publicRole.id,
                },
            });

        // Define the permissions we want to enable
        const permissionsToEnable = [
            { controller: 'hero', action: 'find' },
            { controller: 'section', action: 'find' },
            { controller: 'section', action: 'findOne' },
            { controller: 'feature', action: 'find' },
            { controller: 'feature', action: 'findOne' },
            { controller: 'next-step', action: 'find' },
            { controller: 'next-step', action: 'findOne' },
            { controller: 'community-conference', action: 'find' },
            { controller: 'navbar', action: 'find' },
            { controller: 'navbar', action: 'findOne' },
        ];

        for (const perm of permissionsToEnable) {
            const permission = permissions.find(
                (p) => p.controller === perm.controller && p.action === perm.action
            );

            if (permission && !permission.enabled) {
                await strapi
                    .query('plugin::users-permissions.permission')
                    .update({
                        where: { id: permission.id },
                        data: { enabled: true },
                    });
                console.log(`Enabled ${perm.controller}.${perm.action}`);
            }
        }
    }

    // Populate initial content
    try {
        // Check if Hero already exists
        const heroExists = await strapi.db.query('api::hero.hero').findOne({});

        if (!heroExists) {
            // Create Hero
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
        }

        // Create Sections
        const sectionsExist = await strapi.db.query('api::section.section').findMany({});

        if (sectionsExist.length === 0) {
            const sections = [
                {
                    title: 'Transformieren, wie Ihr Unternehmen arbeitet und L??sungen erstellt',
                    subtitle: 'Erm??glichen Sie Ihren Mitarbeitern, Innovationen voranzutreiben, indem Sie ihnen die Tools an die Hand geben, die sie ben??tigen, um komplexe Probleme zu l??sen.',
                    image_position: 'left',
                    background_color: 'white',
                    publishedAt: new Date(),
                },
                {
                    title: 'Intuitiveres Arbeiten',
                    subtitle: 'Mit Copilot in Microsoft Power Platform k??nnen Sie Gesch??ftsprozesse ganz einfach optimieren und automatisierte Workflows erstellen.',
                    image_position: 'right',
                    background_color: 'light-blue',
                    publishedAt: new Date(),
                },
            ];

            for (const section of sections) {
                await strapi.entityService.create('api::section.section', { data: section });
            }
            console.log('Section content created');
        }

        // Create Features
        const featuresExist = await strapi.db.query('api::feature.feature').findMany({});

        if (featuresExist.length === 0) {
            const features = [
                {
                    title: 'Sprache in Code umwandeln',
                    icon: 'Code',
                    description: 'Erstellen Sie Apps f??r Webanwendungen oder mobile Ger??te mit nat??rlicher Sprache.',
                    publishedAt: new Date(),
                },
                {
                    title: 'Chatbots erstellen',
                    icon: 'MessageSquare',
                    description: 'Erstellen Sie Chatbots mit generativer KI und gro??en Sprachmodellen.',
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
                    description: 'Analysieren Sie Ihre Gesch??ftsprozesse mit detaillierten Einblicken.',
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
                    description: 'Enterprise-Level-Sicherheit f??r Ihre Daten und Anwendungen.',
                    publishedAt: new Date(),
                },
            ];

            for (const feature of features) {
                await strapi.entityService.create('api::feature.feature', { data: feature });
            }
            console.log('Feature content created');
        }

        // Create Next Steps
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
                await strapi.entityService.create('api::next-step.next-step', { data: step });
            }
            console.log('Next Step content created');
        }

        // Create Community Conference
        const communityExists = await strapi.db.query('api::community-conference.community-conference').findOne({});

        if (!communityExists) {
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

        console.log('Bootstrap completed successfully!');
    } catch (error) {
        console.error('Error in bootstrap:', error);
    }
};

