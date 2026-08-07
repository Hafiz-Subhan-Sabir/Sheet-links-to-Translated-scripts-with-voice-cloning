import type { CSSProperties } from "react";

export const CYBER_COLORS = [
  "pink",
  "green",
  "blue",
  "red",
  "gold",
  "orange",
  "purple",
  "cyan",
  "copper",
] as const;

export type CyberColor = (typeof CYBER_COLORS)[number];

export interface CyberTheme {
  color: string;
  glow: string;
  glowSoft: string;
}

/** Neon palette — glow strengths kept subtle for readability on dark UI. */
export const CYBER_THEME: Record<CyberColor, CyberTheme> = {
  pink: {
    color: "#ff2bd6",
    glow: "rgba(255, 43, 214, 0.42)",
    glowSoft: "rgba(255, 43, 214, 0.2)",
  },
  green: {
    color: "#00ff88",
    glow: "rgba(0, 255, 136, 0.42)",
    glowSoft: "rgba(0, 255, 136, 0.2)",
  },
  blue: {
    color: "#00b4ff",
    glow: "rgba(0, 180, 255, 0.42)",
    glowSoft: "rgba(0, 180, 255, 0.2)",
  },
  red: {
    color: "#ff2244",
    glow: "rgba(255, 34, 68, 0.42)",
    glowSoft: "rgba(255, 34, 68, 0.2)",
  },
  gold: {
    color: "#ffd000",
    glow: "rgba(255, 208, 0, 0.42)",
    glowSoft: "rgba(255, 208, 0, 0.2)",
  },
  orange: {
    color: "#ff7a00",
    glow: "rgba(255, 122, 0, 0.42)",
    glowSoft: "rgba(255, 122, 0, 0.2)",
  },
  purple: {
    color: "#b84dff",
    glow: "rgba(184, 77, 255, 0.42)",
    glowSoft: "rgba(184, 77, 255, 0.2)",
  },
  cyan: {
    color: "#00fff5",
    glow: "rgba(0, 255, 245, 0.42)",
    glowSoft: "rgba(0, 255, 245, 0.2)",
  },
  copper: {
    color: "#e8b88a",
    glow: "rgba(232, 184, 138, 0.42)",
    glowSoft: "rgba(232, 184, 138, 0.2)",
  },
};

export function cyberColorForIndex(index: number): CyberColor {
  return CYBER_COLORS[index % CYBER_COLORS.length];
}

export function cyberThemeVars(color: CyberColor): CSSProperties {
  const theme = CYBER_THEME[color];
  return {
    "--cf-color": theme.color,
    "--cf-glow": theme.glow,
    "--cf-glow-soft": theme.glowSoft,
  } as CSSProperties;
}
