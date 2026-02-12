/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#22C55E',
        danger: '#EF4444',
        secondary: '#3B82F6',
        background: '#F5F5F5',
        surface: '#FFFFFF',
        'text-primary': '#374151',
        'text-secondary': '#9CA3AF',
      },
      borderRadius: {
        '2xl': '16px',
      },
    },
  },
  plugins: [],
}
