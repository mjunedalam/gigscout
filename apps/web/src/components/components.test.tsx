import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";
import { describeEvent } from "./describe-event";
import { KindBadge, ScoreRing } from "./badges";
import { EmptyState, StatTile } from "./layout-bits";
import { RunConsole } from "./RunConsole";

describe("components", () => {
  it("stat tile shows label, value and hint", () => {
    renderWithProviders(<StatTile label="Qualified" value={42} hint="ready to pitch" trend={[1, 2, 3]} />);
    expect(screen.getByText("Qualified")).toBeTruthy();
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Qualified trend" })).toBeTruthy();
  });

  it("score ring shows a percentage or a dash", () => {
    renderWithProviders(<><ScoreRing score={0.87} /><ScoreRing score={null} /></>);
    expect(screen.getByText("87")).toBeTruthy();
    expect(screen.getByText("–")).toBeTruthy();
  });

  it("kind badge uses the human label", () => {
    renderWithProviders(<KindBadge kind="hiring" />);
    expect(screen.getByText("Hiring signal")).toBeTruthy();
  });

  it("run console renders the speaker and placeholder", () => {
    renderWithProviders(<RunConsole lines={[]} />);
    expect(screen.getByText("Waiting for the agents…")).toBeTruthy();
    renderWithProviders(<RunConsole lines={[{ line: "scout: searched freelancer" }]} />);
    expect(screen.getByText("scout")).toBeTruthy();
  });

  it("empty state explains what to do", () => {
    renderWithProviders(<EmptyState icon={null} title="No leads">Run the agents.</EmptyState>);
    expect(screen.getByText("Run the agents.")).toBeTruthy();
  });

  it("describes live events in plain language", () => {
    const at = new Date().toISOString();
    expect(describeEvent({ id: 1, type: "run.finished", at, data: { status: "succeeded", new_count: 3, match_count: 2 } }).text)
      .toBe("Run done: 3 new, 2 qualified");
    expect(describeEvent({ id: 2, type: "lead.inbound", at, data: { title: "Inbound enquiry from Clinic" } }).text)
      .toBe("Inbound: Inbound enquiry from Clinic");
  });
});
