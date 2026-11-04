import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Donut } from "./charts/Donut";
import { PipelineFunnel } from "./charts/PipelineFunnel";
import { Sparkline } from "./charts/Sparkline";
import { compactNumber, funnelBars, pushWindow, stackByKind, stackMax } from "./layout";
import { scoreColor } from "./palette";

const rows = [
  { date: "2026-11-01", project: 2, contract: 1, hiring: 0, inbound: 1, signal: 0 },
  { date: "2026-11-02", project: 5, contract: 0, hiring: 3, inbound: 0, signal: 0 },
];

describe("layout helpers", () => {
  it("stacks kinds on top of each other", () => {
    const series = stackByKind(rows);
    expect(series.map((s) => s.key)).toEqual(["project", "contract", "hiring", "inbound", "signal"]);
    expect(stackMax(series)).toBe(8);
    expect([...series[1]![0]!]).toEqual([2, 3]); // contract sits on project on day 1
  });

  it("computes funnel widths and stage conversion", () => {
    const bars = funnelBars([
      { stage: "new", count: 10 },
      { stage: "contacted", count: 4 },
      { stage: "won", count: 1 },
      { stage: "lost", count: 2 },
    ]);
    expect(bars.map((b) => b.width)).toEqual([1, 0.4, 0.1, 0.2]);
    expect(bars.map((b) => b.conversion)).toEqual([null, 0.4, 0.25, null]);
  });

  it("keeps a fixed-size rolling window without mutating", () => {
    const start = [1, 2, 3];
    expect(pushWindow(start, 4, 3)).toEqual([2, 3, 4]);
    expect(start).toEqual([1, 2, 3]);
  });

  it("formats compact numbers and colours scores", () => {
    expect(compactNumber(1530)).toBe("1.5K");
    expect(scoreColor(null)).toBe("#4A5063");
    expect(scoreColor(1)).toBe("rgb(52, 211, 153)");
  });
});

describe("components", () => {
  it("donut labels its total", () => {
    render(<Donut slices={[{ key: "a", label: "A", value: 3, color: "red" }]} caption="leads" />);
    expect(screen.getByRole("img", { name: "Breakdown of 3 leads" })).toBeTruthy();
  });

  it("funnel lists every stage with counts", () => {
    render(<PipelineFunnel stages={[{ stage: "new", count: 5 }, { stage: "won", count: 1 }]} />);
    expect(screen.getByText("new")).toBeTruthy();
    expect(screen.getByText("20%")).toBeTruthy();
  });

  it("sparkline draws once it has two points", () => {
    const { container } = render(<Sparkline values={[1, 3, 2]} label="trend" />);
    expect(container.querySelectorAll("path")).toHaveLength(2);
  });
});
