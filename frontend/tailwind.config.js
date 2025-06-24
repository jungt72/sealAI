/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        // OpenAI-Hausschrift, Fallback auf SystemSans
        sans: ['Söhne', 'Inter', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        // Chat-Hintergrund
        chatBg: '#FFFFFF',           // Main chat area
        userBg: '#FFFFFF',           // User bubble
        assistantBg: '#F7F7F8',      // Assistant bubble
        inputBorder: '#D1D5DB',      // Input-Feld-Rand
        inputFocus: '#10B981',       // Input-Fokusring (emerald-500)
      },
      borderRadius: {
        md: '6px',  // für Message-Bubbles
        lg: '8px',  // für Input-Feld
      },
      fontSize: {
        base: ['16px', '24px'],            // Fließtext
        'xl-title': ['20px', '1.75'],      // Header im Chat
        sm: ['12px', '18px'],              // Kleintexte
      },
      typography: (theme) => ({
        DEFAULT: {
          css: {
            color: theme('colors.gray.800'),
            a: { color: theme('colors.blue.600'), textDecoration: 'underline' },
            strong: { fontWeight: '600' },
            code: {
              backgroundColor: theme('colors.gray.100'),
              padding: '0.2rem 0.4rem',
              borderRadius: '0.25rem',
              fontSize: '0.875em',
            },
            pre: {
              backgroundColor: theme('colors.gray.800'),
              color: theme('colors.white'),
              borderRadius: '0.5rem',
              padding: '1rem',
              overflowX: 'auto',
            },
            h1: { fontSize: '1.5em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '700' },
            h2: { fontSize: '1.25em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '600' },
            h3: { fontSize: '1.1em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '600' },
            ul: { paddingLeft: '1.25em' },
            ol: { paddingLeft: '1.25em' },
            li: { marginTop: '0.25em', marginBottom: '0.25em' },
            blockquote: {
              borderLeft: `4px solid ${theme('colors.blue.300')}`,
              color: theme('colors.gray.500'),
              fontStyle: 'italic',
              paddingLeft: '1em',
              marginTop: '1em',
              marginBottom: '1em',
            },
          },
        },
      }),
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
