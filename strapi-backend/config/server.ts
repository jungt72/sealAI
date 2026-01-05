export default ({ env }) => ({
  url: env('URL', 'https://sealai.net'),
  host: env('HOST', '0.0.0.0'),
  port: env.int('PORT', 1337),
  proxy: true, // wichtig, damit X-Forwarded-* honored wird
  app: {
    keys: env.array('APP_KEYS'),
  },
});
