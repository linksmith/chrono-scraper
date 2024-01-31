/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./chrono_scraper/**/*.{html,js}'],
  theme: {
    extend: {},
  },
  plugins: [require('@tailwindcss/forms')],
};
