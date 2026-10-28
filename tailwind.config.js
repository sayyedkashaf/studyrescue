/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./app/templates/**/*.{html,js}",
    "./app/static/**/*.{html,js,css}",
  ],
  theme: {
    extend: {
      colors: {
        // Core sleek dark-mode SaaS palette
        main: '#0b0f19',
        card: '#111827',
        sidebar: '#111827',
        border: '#1f2937',
        heading: '#f9fafb',
        secondary: '#9ca3af',
        accent: {
          DEFAULT: '#6366f1',
          hover: '#8b5cf6',
          from: '#6366f1',
          to: '#8b5cf6',
        },
        badge: {
          success: {
            text: '#34d399',
            bg: 'rgba(16, 185, 129, 0.12)',
            border: 'rgba(52, 211, 153, 0.25)',
          },
          danger: {
            text: '#f87171',
            bg: 'rgba(239, 68, 68, 0.12)',
            border: 'rgba(248, 113, 113, 0.25)',
          },
          warning: {
            text: '#fbbf24',
            bg: 'rgba(245, 158, 11, 0.12)',
            border: 'rgba(251, 191, 36, 0.25)',
          },
          info: {
            text: '#a5b4fc',
            bg: 'rgba(99, 102, 241, 0.12)',
            border: 'rgba(165, 180, 252, 0.25)',
          },
        },
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        'accent-gradient-hover': 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
      },
      boxShadow: {
        'glow-accent': '0 0 20px -5px rgba(99, 102, 241, 0.4)',
        'card-dark': '0 4px 20px -2px rgba(0, 0, 0, 0.5), 0 0 0 1px #1f2937',
      },
    },
  },
  plugins: [],
};
