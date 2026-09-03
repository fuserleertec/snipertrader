/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0A0E13',
        panel: '#111820',
        panelalt: '#141C25',
        line: '#212B36',
        linesoft: '#1A222C',
        fg: '#E7ECF2',
        muted: '#7C8AA0',
        dim: '#4B5768',
        buy: '#33C77E',
        sell: '#F0555C',
        hold: '#E3A93E',
        k: '#5FA8FF',
        s: '#33C2B8',
        m: '#A98BFF',
        f: '#E3A93E',
        q: '#FF6FB0',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
};
