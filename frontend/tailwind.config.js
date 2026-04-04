/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/login/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Dashboard — Inter via next/font
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        // Landing Page Headlines — Syne via next/font
        syne: ["var(--font-syne)", "ui-sans-serif", "sans-serif"],
        // Landing Page Body — DM Sans via next/font
        body: ["var(--font-dm-sans)", "ui-sans-serif", "sans-serif"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        'seal-platinum': '#E5E7E6',
        'seal-silver': '#778DA9',
        'seal-ylnmn': '#415A77',
        'seal-oxford': '#1B263B',
        'seal-command': '#0f1923',
        'seal-rich': '#0D1B2A',
        // Interaktive Palette (iOS-Blau + Surface + Layout)
        'seal-action':        '#007AFF',
        'seal-action-hover':  '#0066CC',
        'seal-heading':       '#1D1D1F',
        'seal-surface':       '#F5F5F7',
        'seal-surface-hover': '#E5E5EA',
        'seal-bg':            '#eef4fb',
        'seal-bg-light':      '#f7fbff',
        'gemini-bg':          '#EAF0F9',
        platinum: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        industrial: {
          blue: "#0ea5e9",
          cyan: "#06b6d4",
          amber: "#f59e0b",
          emerald: "#10b981",
        }
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "industrial-gradient": "linear-gradient(to bottom right, #0f172a, #1e293b)",
        // Dashboard-Hintergrund: sanfter Verlauf von seal-bg-light nach seal-bg
        "seal-dashboard": "radial-gradient(ellipse at top, #f7fbff 0%, #eef4fb 100%)",
        // CaseScreen-Hintergrund: blauer Radial-Glow (#007AFF, 9% opacity) über linearem Verlauf
        "seal-overlay": "radial-gradient(circle at top left, rgba(0,122,255,0.09), transparent 34%), linear-gradient(180deg, #f7fbff 0%, #eef4fb 100%)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.25s ease-out both",
      },
    },
  },
  plugins: [],
};
