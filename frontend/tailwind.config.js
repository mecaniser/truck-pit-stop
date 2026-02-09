/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Super Admin theme (gold/noir)
        gold: {
          400: '#D4A84B',
          500: '#B8860B',
          600: '#9A7209',
          700: '#7C5C07',
        },
        noir: {
          900: '#0a0a0f',
          800: '#12121a',
          700: '#1a1a24',
        },
        // BlueNoir theme base (dark with blue undertone)
        blueNoir: {
          900: '#0a0f14',
          800: '#101820',
          700: '#182028',
        },
        // Theme accent colors (5 distinct options)
        accent: {
          cyan: {
            400: '#22D3EE',
            500: '#06B6D4',
            600: '#0891B2',
          },
          indigo: {
            400: '#818CF8',
            500: '#6366F1',
            600: '#4F46E5',
          },
          emerald: {
            400: '#34D399',
            500: '#10B981',
            600: '#059669',
          },
          rose: {
            400: '#FB7185',
            500: '#F43F5E',
            600: '#E11D48',
          },
          amber: {
            400: '#FBBF24',
            500: '#F59E0B',
            600: '#D97706',
          },
        },
      }
    },
  },
  plugins: [],
}


