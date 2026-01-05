// frontend/next.config.mjs
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // erzeugt .next/standalone für schlanke Docker-Runner-Images
  output: 'standalone',

  // TypeScript: aktuell werden Build-Fehler ignoriert.
  // Für saubere Produktion solltest du das später auf `false` setzen
  // und die Typfehler wirklich fixen.
  typescript: {
    ignoreBuildErrors: true,
  },

  experimental: {
    // hier kannst du bei Bedarf weitere Flags hinzufügen
  },
}

export default nextConfig
