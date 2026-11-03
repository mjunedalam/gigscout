import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Signal lime: the brand accent (primary actions, "live", qualified). Generated around #C6F432.
const signal: MantineColorsTuple = [
  "#f8fee6", "#effccc", "#dff99a", "#cff663", "#c6f432", "#b7e81b", "#a2cf0c", "#7fa300", "#5f7a00", "#3f5200",
];

// Ink: the neutral ramp for the dark theme (Mantine's "dark" palette).
const ink: MantineColorsTuple = [
  "#eceef4", "#c4c8d3", "#8a90a2", "#636a7e", "#3a4153", "#252b3b", "#1a1f2d", "#141824", "#0f1219", "#0b0d12",
];

const violet: MantineColorsTuple = [
  "#f0eeff", "#dcd7ff", "#b7adff", "#9887ff", "#8b7cff", "#7666f2", "#5f4fd9", "#4b3cb3", "#3a2e8c", "#2a2166",
];

export const theme = createTheme({
  primaryColor: "signal",
  primaryShade: { light: 7, dark: 4 },
  colors: { signal, dark: ink, violet },
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
    Button: { defaultProps: { radius: "xl" } },
    ActionIcon: { defaultProps: { variant: "subtle", radius: "xl" } },
    Badge: { defaultProps: { radius: "sm", variant: "light" }, styles: { label: { letterSpacing: "0.04em" } } },
    Paper: { defaultProps: { radius: "lg" } },
    Card: { defaultProps: { radius: "lg" } },
    Modal: { defaultProps: { radius: "lg", overlayProps: { backgroundOpacity: 0.6, blur: 6 } } },
    Drawer: { defaultProps: { overlayProps: { backgroundOpacity: 0.5, blur: 4 } } },
    Tooltip: { defaultProps: { withArrow: true, openDelay: 250 } },
    TextInput: { defaultProps: { radius: "md" } },
    Table: { defaultProps: { verticalSpacing: "sm", highlightOnHover: true } },
  },
});
