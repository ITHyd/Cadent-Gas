/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Nunito', 'Calibri', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        heading: ['Playfair Display', 'Times New Roman', 'serif'],
      },
      fontSize: {
        'hero': ['48px', { lineHeight: '1.2', letterSpacing: '-0.5px', fontWeight: '700' }],
        'section': ['32px', { lineHeight: '1.3', letterSpacing: '-0.5px', fontWeight: '600' }],
        'card-title': ['20px', { lineHeight: '1.4', letterSpacing: '-0.25px', fontWeight: '600' }],
        'body': ['16px', { lineHeight: '1.6', fontWeight: '400' }],
      },
      boxShadow: {
        soft: '0 12px 40px -18px rgba(3, 3, 4, 0.30)',
      },
      colors: {
        brand: {
          50: '#F6F2F4',
          100: '#E8E0F0',
          200: '#D4C8E2',
          300: '#AD96DC',
          400: '#8DE971',
          500: '#7BD45F',
          600: '#65B84D',
          700: '#4A9438',
          800: '#030304',
          900: '#000000',
        },
        nxzen: {
          black: '#030304',
          green: '#8DE971',
          violet: '#AD96DC',
          pearl: '#F6F2F4',
          yellow: '#ECF166',
          blue: '#74D1EA',
          pink: '#FF7276',
        },
      },
    },
  },
  plugins: [],
};
