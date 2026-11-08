import type { MantineThemeOverride } from "@mantine/core";
import { createContext, useContext } from "react";

import { ACCENTS, type AccentName, DEFAULT_ACCENT } from "./accents";
import { createAppTheme } from "./theme";

export { ACCENTS, DEFAULT_ACCENT, type AccentName } from "./accents";

/** A stored accent is untrusted input (old versions, hand edits): keep it only if we know it. */
export function resolveAccent(value: unknown): AccentName {
  return typeof value === "string" && value in ACCENTS ? (value as AccentName) : DEFAULT_ACCENT;
}

export function buildTheme(accent: AccentName): MantineThemeOverride {
  return createAppTheme(ACCENTS[accent].scale);
}

export interface AppearanceValue {
  accent: AccentName;
  setAccent: (accent: AccentName) => void;
}

export const AppearanceContext = createContext<AppearanceValue>({ accent: DEFAULT_ACCENT, setAccent: () => {} });

export function useAppearance(): AppearanceValue {
  return useContext(AppearanceContext);
}
