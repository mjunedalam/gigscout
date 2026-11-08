import type { MapPoint } from "@gigscout/api-client";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test/render";
import { FlatGalaxy } from "./galaxy/FlatGalaxy";
import { canUseWebGL } from "./galaxy/webgl";
import { RouteErrorView } from "./RouteError";

const POINTS: MapPoint[] = [
  { id: "a", title: "Clinic booking app", kind: "project", source: "freelancer", x: -1, y: 0.5, z: 0, score: 0.8 },
  { id: "b", title: "Head of Engineering", kind: "hiring", source: "remotive", x: 1, y: -0.5, z: 0, score: null },
];

describe("galaxy without WebGL", () => {
  it("detects that jsdom cannot draw WebGL", () => {
    expect(canUseWebGL()).toBe(false);
  });

  it("flat galaxy plots every lead and opens one on click", () => {
    const onSelect = vi.fn();
    renderWithProviders(<FlatGalaxy points={POINTS} height={300} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Clinic booking app/ }));
    expect(onSelect).toHaveBeenCalledWith("a");
    expect(screen.getByRole("button", { name: /Head of Engineering/ })).toBeTruthy();
  });
});

describe("route error", () => {
  it("explains what broke and offers a way out", () => {
    renderWithProviders(<RouteErrorView message="Error creating WebGL context." />);
    expect(screen.getByText("This screen hit a snag")).toBeTruthy();
    expect(screen.getByText("Error creating WebGL context.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to command center" })).toBeTruthy();
  });
});
