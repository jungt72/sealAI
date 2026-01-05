// Script to update Strapi permissions for new content types
// Run this inside the Strapi container with: node update-permissions.js

const axios = require('axios');

const STRAPI_URL = 'http://localhost:1337';
const ADMIN_EMAIL = 'mail@thorsten-jung.de';
const ADMIN_PASSWORD = 'Katerkimba!1';

async function updatePermissions() {
    try {
        // Login to get JWT token
        console.log('Logging in to Strapi...');
        const loginResponse = await axios.post(`${STRAPI_URL}/admin/login`, {
            email: ADMIN_EMAIL,
            password: ADMIN_PASSWORD
        });

        const token = loginResponse.data.data.token;
        console.log('Login successful!');

        // Get all roles
        console.log('Fetching roles...');
        const rolesResponse = await axios.get(`${STRAPI_URL}/admin/users/roles`, {
            headers: { Authorization: `Bearer ${token}` }
        });

        const publicRole = rolesResponse.data.data.find(role => role.type === 'public');

        if (!publicRole) {
            console.error('Public role not found!');
            return;
        }

        console.log(`Found public role: ${publicRole.id}`);

        // Set permissions for intro-headline
        console.log('Setting permissions for intro-headline...');
        await axios.put(`${STRAPI_URL}/admin/permissions`, {
            permissions: {
                'api::intro-headline': {
                    controllers: {
                        'intro-headline': {
                            find: { enabled: true },
                            findOne: { enabled: true }
                        }
                    }
                }
            },
            role: publicRole.id
        }, {
            headers: { Authorization: `Bearer ${token}` }
        });

        // Set permissions for product-tabs
        console.log('Setting permissions for product-tabs...');
        await axios.put(`${STRAPI_URL}/admin/permissions`, {
            permissions: {
                'api::product-tab': {
                    controllers: {
                        'product-tab': {
                            find: { enabled: true },
                            findOne: { enabled: true }
                        }
                    }
                }
            },
            role: publicRole.id
        }, {
            headers: { Authorization: `Bearer ${token}` }
        });

        console.log('Permissions updated successfully!');

    } catch (error) {
        console.error('Error updating permissions:', error.response?.data || error.message);
    }
}

updatePermissions();
