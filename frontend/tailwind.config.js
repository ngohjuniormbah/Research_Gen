/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0B0E13',
          900: '#0F131A',
          850: '#131822',
          800: '#161C27',
          700: '#1E2631',
          600: '#2A3441',
          500: '#3C4859',
        },
        mist: {
          400: '#5B6B7F',
          300: '#8593A6',
          200: '#AEBACC',
          100: '#D7DEE8',
          50: '#EEF2F7',
        },
        signal: {
          teal: '#4FE3C1',
          tealDim: '#2E8A78',
          amber: '#F0A94E',
          coral: '#F0705F',
          violet: '#8B7CF0',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"Inter"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      backgroundImage: {
        'graph-grid':
          'radial-gradient(circle at 1px 1px, rgba(79,227,193,0.08) 1px, transparent 0)',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(79,227,193,0.15), 0 0 24px rgba(79,227,193,0.08)',
      },
      keyframes: {
        pulseDot: {
          '0%, 100%': { opacity: '0.3', transform: 'scale(0.85)' },
          '50%': { opacity: '1', transform: 'scale(1)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        pulseDot: 'pulseDot 1.4s ease-in-out infinite',
        slideUp: 'slideUp 0.22s ease-out',
      },
    },
  },
  plugins: [],
};
