import { MantineProvider } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { type ReactNode, useLayoutEffect, useMemo } from "react";

import { ACCENTS, type AccentName, DARK_SHADE, DEFAULT_ACCENT, LIGHT_SHADE } from "./accents";
import { AppearanceContext, buildTheme, resolveAccent } from "./appearance-context";

const STORAGE_KEY = "gs-accent";

interface AppearanceProviderProps {
  children: ReactNode;
}

/** Wraps MantineProvider so the accent the viewer picked repaints Mantine colours and our CSS tokens together. */
export function AppearanceProvider({ children }: AppearanceProviderProps) {
  const [stored, setStored] = useLocalStorage<string>({ key: STORAGE_KEY, defaultValue: DEFAULT_ACCENT });
  const accent = resolveAccent(stored);
  const theme = useMemo(() => buildTheme(accent), [accent]);

  // global.css reads these for --gs-signal in each colour scheme
  useLayoutEffect(() => {
    const { scale } = ACCENTS[accent];
    const root = document.documentElement;
    root.style.setProperty("--gs-accent-dark", scale[DARK_SHADE]);
    root.style.setProperty("--gs-accent-light", scale[LIGHT_SHADE]);
    root.dataset.gsAccent = accent;
  }, [accent]);

  const value = useMemo(() => ({ accent, setAccent: (next: AccentName) => setStored(next) }), [accent, setStored]);

  return (
    <AppearanceContext.Provider value={value}>
      <MantineProvider theme={theme} defaultColorScheme="dark">
        {children}
      </MantineProvider>
    </AppearanceContext.Provider>
  );
}
