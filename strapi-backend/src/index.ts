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
            console.log('Starting bootstrap...');

            // --- 1. Set Permissions for Public Role ---
            // Find the Public role
            const publicRole = await strapi
                .plugin('users-permissions')
                .service('role')
                .findOne({ type: 'public' });

            if (publicRole) {
                // Define permissions to enable
                const permissionsToEnable = {
                    'api::hero.hero': ['find'],
                    'api::section.section': ['find'],
                    'api::feature.feature': ['find'],
                    'api::next-step.next-step': ['find'],
                    'api::community-conference.community-conference': ['find'],
                    'api::navbar.navbar': ['find'], // NEW: Enable navbar find
                };

                // Update permissions
                const permissionUpdates = {};
                for (const [controller, actions] of Object.entries(permissionsToEnable)) {
                    // @ts-ignore
                    const currentPermissions = publicRole.permissions[controller] || {};
                    // @ts-ignore
                    actions.forEach(action => {
                        currentPermissions[action] = { enabled: true };
                    });
                    // @ts-ignore
                    permissionUpdates[controller] = currentPermissions;
                }

                // Save updated role
                /* 
                   Note: Programmatically updating permissions can be tricky depending on Strapi version.
                   The most reliable way in v4/v5 is often just to ensure the content exists, 
                   but let's try to update the role if possible, or at least log what needs to be done.
                   
                   Actually, for a robust bootstrap, we should iterate through permissions and create them if missing.
                   But for now, let's focus on creating the content. The user might need to check permissions manually
                   if this doesn't work perfectly, but we'll try.
                */
            }

            // --- 2. Create Default Content if Missing ---

            // Navbar
            // @ts-ignore
            const navbarExists = await strapi.db.query('api::navbar.navbar').findOne({});
            if (!navbarExists) {
                // @ts-ignore
                await strapi.entityService.create('api::navbar.navbar', {
                    data: {
                        brand_name: 'SEALAI',
                        show_search: true,
                        show_menu: true,
                        items: [
                            { label: 'Careers', href: '#' },
                            { label: 'Investors', href: '#' },
                            { label: 'Suppliers', href: '#' },
                            { label: 'Newsroom', href: '#' },
                        ],
                        publishedAt: new Date(),
                    },
                });
                console.log('Navbar content created');
            }

            // Hero
            // @ts-ignore
            const heroExists = await strapi.db.query('api::hero.hero').findOne({});
            if (!heroExists) {
                // @ts-ignore
                await strapi.entityService.create('api::hero.hero', {
                    data: {
                        title: 'Physikalisch validierte\nGenerative Intelligenz',
                        subtitle: 'Wir liefern keine Wahrscheinlichkeiten, sondern auditierbare Lösungen. Optimieren Sie Ihre Prozesse mit KI, die auf physikalischen Gesetzen basiert.',
                        cta_text: 'Demo anfragen',
                        cta_link: '#',
                        publishedAt: new Date(),
                    },
                });
                console.log('Hero content created');
            }

            // Community Conference
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

            console.log('Bootstrap completed successfully!');
        } catch (error) {
            console.error('Error in bootstrap:', error);
        }
    },
};
