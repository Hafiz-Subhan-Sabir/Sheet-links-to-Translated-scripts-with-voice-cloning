import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        muted: "var(--muted)",
        "muted-foreground": "var(--muted-foreground)",
        border: "var(--border)",
        card: "var(--card)",
        "card-foreground": "var(--card-foreground)",
        accent: "var(--accent)",
        "accent-secondary": "var(--accent-secondary)",
        "accent-foreground": "var(--accent-foreground)",
        ring: "var(--ring)",
        "surface-muted": "var(--surface-muted)",
        gold: "var(--gold)",
        "accent-tertiary": "var(--accent-tertiary)",
        "accent-warm": "var(--accent-warm)",
        "accent-rose": "var(--accent-rose)",
      },
      boxShadow: {
        glow: "0 0 28px -14px var(--glow)",
        "glow-sm": "0 0 14px -8px var(--glow)",
      },
      animation: {
        shimmer: "shimmer 2s infinite",
        "fade-in-up": "fade-in-up 0.6s cubic-bezier(0.22, 1, 0.36, 1) both",
        "scale-in": "scale-in 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "border-glow": "border-glow 2.5s ease-in-out infinite",
        "float-orb": "float-orb 12s ease-in-out infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(20px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "border-glow": {
          "0%, 100%": { boxShadow: "0 0 10px -6px rgba(34, 211, 238, 0.16)" },
          "50%": { boxShadow: "0 0 14px -6px rgba(167, 139, 250, 0.18)" },
        },
        "float-orb": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(12px, -16px) scale(1.05)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
