/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#FAFAF8',
        surface: '#FFFFFF',
        subtle: '#F3F3EF',
        ink: {
          DEFAULT: '#1C1D1F',
          muted: '#525458',
          faint: '#76787C',
        },
        accent: {
          DEFAULT: '#0B4F8A',
          hover: '#083D6B',
          tint: '#EDF4FA',
        },
        line: '#E4E4E0',
        qc: {
          green: '#1E7B4F',
          greenBg: '#EAF4EE',
          greenBorder: '#B8DFC9',
          amber: '#A86A00',
          amberBg: '#FDF5E6',
          amberBorder: '#F0D49B',
          red: '#B42318',
          redBg: '#FDECEB',
          redBorder: '#F5BDBA',
        },
      },
      fontFamily: {
        serif: ['"Source Serif 4"', 'Georgia', ' Cambria', 'serif'],
        sans: ['"Source Sans 3"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '6px',
        card: '8px',
      },
    },
  },
  plugins: [],
};
