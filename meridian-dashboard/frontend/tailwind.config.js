/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        signal: {
          buy: 'rgb(var(--signal-buy) / <alpha-value>)',
          sell: 'rgb(var(--signal-sell) / <alpha-value>)',
          neutral: 'rgb(var(--signal-neutral) / <alpha-value>)',
          amber: 'rgb(var(--signal-amber) / <alpha-value>)',
        },
        term: {
          bg: 'rgb(var(--term-bg) / <alpha-value>)',
          surface: 'rgb(var(--term-surface) / <alpha-value>)',
          surface2: 'rgb(var(--term-surface2) / <alpha-value>)',
          line: 'rgb(var(--term-line) / <alpha-value>)',
          text: 'rgb(var(--term-text) / <alpha-value>)',
          muted: 'rgb(var(--term-muted) / <alpha-value>)',
          faint: 'rgb(var(--term-faint) / <alpha-value>)',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
