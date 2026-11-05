import type { PipelineStep } from "@gigscout/api-client";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/render";
import { change, usd, waitLabel } from "../../lib/format";
import { StageFlow } from "./StageFlow";

const step = (stage: PipelineStep["stage"], label: string, extra: Partial<PipelineStep> = {}): PipelineStep => ({
  stage, label, count: 0, previous: 0, conversion: null, median_hours: null, waiting: 0, stale: 0, ...extra,
});

const STEPS: PipelineStep[] = [
  step("found", "Found", { count: 40, previous: 20, waiting: 12 }),
  step("qualified", "Qualified", { count: 10, previous: 10, conversion: 0.25, median_hours: 2 }),
  step("sent", "Sent", { count: 4, conversion: 0.4, median_hours: 72, waiting: 3, stale: 2 }),
  step("lost", "Lost", { count: 1 }),
];

describe("pipeline strip", () => {
  afterEach(cleanup);

  it("shows counts, change, conversion, waits and stuck leads, and picks a step", () => {
    const onSelect = vi.fn();
    renderWithProviders(<StageFlow steps={STEPS} selected={null} onSelect={onSelect} />);
    expect(screen.getByText("40")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy(); // found doubled
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.getByText("3 d to get here")).toBeTruthy();
    expect(screen.getByText("3 here now · 2 stuck")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Sent/ }));
    expect(onSelect).toHaveBeenCalledWith("sent");
  });
});

describe("report formatting", () => {
  it("says waits, money and change the way people do", () => {
    expect(waitLabel(0.25)).toBe("15 min");
    expect(waitLabel(30)).toBe("30 h");
    expect(waitLabel(96)).toBe("4 d");
    expect(waitLabel(null)).toBe("—");
    expect(usd(12500)).toBe("$12,500");
    expect(usd(1_250_000, true)).toBe("$1.3M");
    expect(change(15, 10)).toBe(50);
    expect(change(0, 0)).toBe(0);
    expect(change(3, 0)).toBeNull();
  });
});
