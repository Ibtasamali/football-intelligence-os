/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk"', "Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: { 950: "#04060b", 900: "#070b14", 850: "#0a0f1c", 800: "#0e1526", 700: "#162036", 600: "#22304d" },
        azure: { DEFAULT: "#3BA4F6", glow: "#7cc4ff" },
        thames: { DEFAULT: "#F2555A" },
        signal: { cyan: "#22D3EE", gold: "#FACC15", violet: "#A78BFA", orange: "#F97316", green: "#34D399" },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(124,196,255,.15), 0 10px 40px -10px rgba(34,211,238,.25)",
      },
      keyframes: {
        sweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
      },
      animation: { sweep: "sweep 2.4s linear infinite" },
    },
  },
  plugins: [],
};
