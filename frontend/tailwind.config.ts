import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07080d",
          900: "#0b0d14",
          850: "#0f1219",
          800: "#141822",
          700: "#1c212e",
          600: "#272e3e",
          500: "#3a4356",
          400: "#5a6478",
        },
        accent: {
          DEFAULT: "#7c5cff",
          soft: "#a48bff",
          deep: "#5b3ce6",
        },
        signal: {
          cyan: "#38e0d6",
          amber: "#ffb43d",
          rose: "#ff5d7a",
          lime: "#8ef07a",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,.04) inset, 0 20px 60px -20px rgba(0,0,0,.8)",
        glow: "0 0 0 1px rgba(124,92,255,.35), 0 12px 40px -12px rgba(124,92,255,.55)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(124,92,255,.18), transparent 70%)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseRing: {
          "0%": { boxShadow: "0 0 0 0 rgba(124,92,255,.45)" },
          "100%": { boxShadow: "0 0 0 12px rgba(124,92,255,0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.8s infinite",
        "fade-up": "fade-up .35s cubic-bezier(.2,.7,.3,1) both",
        "pulse-ring": "pulseRing 1.8s ease-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
