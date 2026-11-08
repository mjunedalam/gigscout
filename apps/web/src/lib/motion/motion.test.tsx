import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedNumber } from "./AnimatedNumber";
import { formatCount } from "./count";
import { SplitWords } from "./SplitWords";
import { splitWords } from "./words";

describe("splitWords", () => {
  it("splits on whitespace and drops empty pieces", () => {
    expect(splitWords("  Where your   next clients are ")).toEqual(["Where", "your", "next", "clients", "are"]);
  });

  it("returns nothing for an empty string", () => {
    expect(splitWords("   ")).toEqual([]);
  });
});

describe("SplitWords", () => {
  it("keeps the full sentence readable as text", () => {
    render(<h1><SplitWords text="Get there first." /></h1>);
    expect(screen.getByRole("heading").textContent).toBe("Get there first.");
  });
});

describe("formatCount", () => {
  it("groups thousands and rounds to whole numbers", () => {
    expect(formatCount(12345.6)).toBe("12,346");
    expect(formatCount(0)).toBe("0");
  });
});

describe("AnimatedNumber", () => {
  it("renders the final value straight away when motion is off (jsdom has no animation frames to wait on)", () => {
    render(<AnimatedNumber value={710} />);
    expect(screen.getByText("710")).toBeTruthy();
  });
});
