/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class'],
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Söhne', 'Inter', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        chatBg: '#FFFFFF',
        userBg: '#FFFFFF',
        assistantBg: '#F7F7F8',
        inputBorder: '#D1D5DB',
        inputFocus: '#10B981',

        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',

        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },

        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',

        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))',
        },
      },
      borderRadius: {
        md: 'calc(var(--radius) - 2px)',
        lg: 'var(--radius)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontSize: {
        base: ['16px', '24px'],
        'xl-title': ['20px', '1.75'],
        sm: ['12px', '18px'],
      },

      // FIX: muss echte Funktion sein, kein String
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
  plugins: [
    require('@tailwindcss/typography'),
    require('tailwindcss-animate'),
  ],
}
