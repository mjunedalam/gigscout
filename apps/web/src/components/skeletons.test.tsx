import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardSkeleton, ListSkeleton, TableSkeleton } from "./skeletons";

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

describe("skeletons", () => {
  it("announce what is loading once, through a busy status region", () => {
    wrap(<TableSkeleton label="Loading leads" />);
    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(status.textContent).toBe("Loading leads");
  });

  it("draw one column per pipeline stage", () => {
    const { container } = wrap(<BoardSkeleton />);
    expect(container.querySelectorAll(".gs-column")).toHaveLength(6);
  });

  it("draw the number of rows asked for", () => {
    const { container } = wrap(<ListSkeleton rows={3} />);
    expect(container.querySelectorAll(".gs-panel")).toHaveLength(3);
  });
});
