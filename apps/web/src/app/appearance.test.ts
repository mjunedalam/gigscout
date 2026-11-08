import { describe, expect, it } from "vitest";

import { ACCENTS, DEFAULT_ACCENT, buildTheme, resolveAccent } from "./appearance-context";

describe("resolveAccent", () => {
  it("keeps a known accent", () => {
    expect(resolveAccent("iris")).toBe("iris");
  });

  it("falls back to the default for anything unknown or missing", () => {
    expect(resolveAccent("hotpink")).toBe(DEFAULT_ACCENT);
    expect(resolveAccent(null)).toBe(DEFAULT_ACCENT);
    expect(resolveAccent(undefined)).toBe(DEFAULT_ACCENT);
  });
});

describe("buildTheme", () => {
  it("paints the signal colour from the chosen accent", () => {
    const theme = buildTheme("lime");
    expect(theme.colors?.signal).toEqual(ACCENTS.lime.scale);
  });

  it("every accent has a full ten-step scale", () => {
    for (const accent of Object.values(ACCENTS)) expect(accent.scale).toHaveLength(10);
  });
});
