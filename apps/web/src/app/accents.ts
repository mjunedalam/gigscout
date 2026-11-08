import type { MantineColorsTuple } from "@mantine/core";

/*
 * Accent palettes for the "signal" role (live, healthy, qualified, switched on). Each is a ten-step scale:
 * shade 4 is the accent on the dark theme, shade 7 on the light theme. None is red or amber, so the accent never
 * reads as an error or a warning.
 */
export type AccentName = "emerald" | "iris" | "lime" | "sky";

export interface Accent {
  label: string;
  scale: MantineColorsTuple;
}

export const ACCENTS: Record<AccentName, Accent> = {
  emerald: {
    label: "Emerald",
    scale: ["#ecfdf5", "#d1fae5", "#a7f3d0", "#6ee7b7", "#34d399", "#10b981", "#059669", "#047857", "#065f46", "#064e3b"],
  },
  iris: {
    label: "Iris",
    scale: ["#eef0ff", "#dfe3ff", "#c0c8ff", "#a0acff", "#8b9cff", "#6f7ff5", "#5a66e0", "#4650c0", "#363d96", "#272c6b"],
  },
  lime: {
    label: "Lime",
    scale: ["#f7fee7", "#ecfccb", "#d9f99d", "#bef264", "#a3e635", "#84cc16", "#65a30d", "#4d7c0f", "#3f6212", "#365314"],
  },
  sky: {
    label: "Sky",
    scale: ["#f0f9ff", "#e0f2fe", "#bae6fd", "#7dd3fc", "#38bdf8", "#0ea5e9", "#0284c7", "#0369a1", "#075985", "#0c4a6e"],
  },
};

export const DEFAULT_ACCENT: AccentName = "emerald";
export const DARK_SHADE = 4;
export const LIGHT_SHADE = 7;
