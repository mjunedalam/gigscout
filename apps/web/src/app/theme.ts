import { createTheme, defaultVariantColorsResolver, type MantineColorsTuple, type VariantColorsResolver } from "@mantine/core";

import { ACCENTS, DARK_SHADE, DEFAULT_ACCENT, LIGHT_SHADE } from "./accents";

/*
 * Colour roles
 * - brand: actions. Buttons are high-contrast neutrals (near-white on dark, near-black on light), so an action never
 *   competes with data for colour. Light/subtle variants are quiet greys.
 * - signal: meaning. The accent (emerald by default, see accents.ts) marks what is live, healthy, qualified or switched on (mint on dark, deep on light).
 * - lead kinds and agents keep their own fixed hues for charts and the cockpit.
 */
const brand: MantineColorsTuple = [
  "#f7f8fa", "#eceef3", "#d5d9e2", "#b4bac8", "#8a91a3", "#5f6678", "#3d4352", "#262b37", "#181c25", "#0f1218",
];


// Ink: the neutral ramp for the dark theme (Mantine's "dark" palette).
const ink: MantineColorsTuple = [
  "#eceef4", "#c4c8d3", "#8a90a2", "#636a7e", "#3a4153", "#252b3b", "#1a1f2d", "#141824", "#0f1219", "#0b0d12",
];

const violet: MantineColorsTuple = [
  "#f0eeff", "#dcd7ff", "#b7adff", "#9887ff", "#8b7cff", "#7666f2", "#5f4fd9", "#4b3cb3", "#3a2e8c", "#2a2166",
];

/** Brand buttons read CSS tokens (see global.css), so they invert cleanly between the light and dark themes. */
const variantColorResolver: VariantColorsResolver = (input) => {
  if (input.color === "brand" || (input.color === undefined && input.theme.primaryColor === "brand")) {
    if (input.variant === "filled") {
      return { background: "var(--gs-btn-bg)", hover: "var(--gs-btn-bg-hover)", color: "var(--gs-btn-fg)", hoverColor: "var(--gs-btn-fg)", border: "none" };
    }
    if (input.variant === "light") {
      return { background: "var(--gs-btn-soft)", hover: "var(--gs-btn-soft-hover)", color: "var(--gs-text)", hoverColor: "var(--gs-text)", border: "none" };
    }
  }
  return defaultVariantColorsResolver(input);
};

const accent = { defaultProps: { color: "signal" } };

/** The app theme with the signal role painted from the given accent scale (see accents.ts). */
export function createAppTheme(signal: MantineColorsTuple) {
  return createTheme({
    primaryColor: "brand",
    primaryShade: { light: LIGHT_SHADE, dark: DARK_SHADE },
    colors: { brand, signal, dark: ink, violet },
    variantColorResolver,
    fontFamily: "var(--gs-font-text)",
    fontFamilyMonospace: "var(--gs-font-mono)",
    headings: {
      fontFamily: "var(--gs-font-display)",
      fontWeight: "600",
      sizes: {
        h1: { fontSize: "clamp(1.9rem, 1.4rem + 1.6vw, 2.75rem)", lineHeight: "1.05" },
        h2: { fontSize: "clamp(1.35rem, 1.15rem + 0.8vw, 1.75rem)", lineHeight: "1.15" },
        h3: { fontSize: "1.15rem", lineHeight: "1.25" },
      },
    },
    defaultRadius: "md",
    radius: { xs: "4px", sm: "6px", md: "10px", lg: "16px", xl: "24px" },
    cursorType: "pointer",
    focusRing: "auto",
    autoContrast: true,
    luminanceThreshold: 0.45,
    components: {
      Button: { defaultProps: { radius: "xl" }, styles: { root: { fontWeight: 600, letterSpacing: "-0.005em" } } },
      ActionIcon: { defaultProps: { variant: "subtle", radius: "xl" } },
      Badge: { defaultProps: { radius: "sm", variant: "light" }, styles: { label: { letterSpacing: "0.04em" } } },
      // controls that show a state (on, checked, progress) use the meaning colour, not the action colour
      Switch: accent,
      Checkbox: accent,
      Radio: accent,
      Slider: accent,
      Progress: accent,
      Loader: accent,
      Paper: { defaultProps: { radius: "lg" } },
      Card: { defaultProps: { radius: "lg" } },
      Modal: { defaultProps: { radius: "lg", overlayProps: { backgroundOpacity: 0.6, blur: 6 } } },
      Drawer: { defaultProps: { overlayProps: { backgroundOpacity: 0.5, blur: 4 } } },
      Tooltip: { defaultProps: { withArrow: true, openDelay: 250 } },
      TextInput: { defaultProps: { radius: "md" } },
      Table: { defaultProps: { verticalSpacing: "sm", highlightOnHover: true } },
    },
  });
}

export const theme = createAppTheme(ACCENTS[DEFAULT_ACCENT].scale);
