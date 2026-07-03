/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        tg_bg: 'var(--tg-theme-bg-color)',
        tg_text: 'var(--tg-theme-text-color)',
        tg_hint: 'var(--tg-theme-hint-color)',
        tg_link: 'var(--tg-theme-link-color)',
        tg_button: 'var(--tg-theme-button-color)',
        tg_button_text: 'var(--tg-theme-button-text-color)',
        tg_secondary_bg: 'var(--tg-theme-secondary-bg-color)',
      },
      fontFamily: {
        vazir: ['Vazirmatn', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
