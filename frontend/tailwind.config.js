/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0040e0',
          container: '#2e5bff',
          hover: '#1a41cc',
          fixed: '#dde1ff',
          'fixed-dim': '#b8c3ff',
          'on-container': '#efefff',
        },
        secondary: {
          DEFAULT: '#585e6b',
          container: '#dae0ef',
          'on-container': '#5d636f',
        },
        tertiary: {
          DEFAULT: '#993100',
          container: '#c24100',
          fixed: '#ffdbcf',
        },
        surface: {
          DEFAULT: '#ffffff',
          dim: '#dbdad6',
          bright: '#fbf9f5',
          container: '#f0eeea',
          'container-low': '#f5f3ef',
          'container-high': '#eae8e4',
          'container-highest': '#e4e2de',
          'container-lowest': '#ffffff',
        },
        'on-surface': '#1b1c1a',
        'on-surface-variant': '#434656',
        'outline-variant': '#c4c5d9',
        border: '#e5e7eb',
        background: '#f4f2ee',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.8s ease-out forwards',
      },
    },
  },
  plugins: [],
}