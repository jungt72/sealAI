export default ({ env }) => ({
  url: env('ADMIN_URL', '/admin'),     // Subpfad
  serveAdminPanel: env.bool('SERVE_ADMIN', true),
  auth: {
    secret: env('ADMIN_AUTH_SECRET', env('ADMIN_JWT_SECRET')),
  },
});
