/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",         // Next.js App-Router
    "./pages/**/*.{js,ts,jsx,tsx}",       // Für ältere Pages-Verzeichnisse
    "./components/**/*.{js,ts,jsx,tsx}",  // Alle Deine gemeinsamen Komponenten
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
