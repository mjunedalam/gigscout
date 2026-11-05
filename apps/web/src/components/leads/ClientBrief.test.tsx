import type { LeadBrief } from "@gigscout/api-client";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/render";
import { BriefCard } from "./ClientBrief";

const BRIEF: LeadBrief = {
  lead_id: "x:1", website: "javascript:alert(1)", tech: ["Next.js"], made_by: "ai", created_by: "a", created_at: "2026-11-06T10:00:00Z",
  brief: { summary: "Clinic Group runs 12 clinics.", needs: [], signals: [], talking_points: ["They use Next.js"], risks: [] },
  sources: [{ label: "Home", url: "https://clinicgroup.com" }, { label: "Evil", url: "javascript:alert(1)" }],
};

describe("client brief", () => {
  afterEach(cleanup);

  it("shows the brief and links only to web addresses", () => {
    renderWithProviders(<BriefCard brief={BRIEF} />);
    expect(screen.getByText("Clinic Group runs 12 clinics.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Home" }).getAttribute("href")).toBe("https://clinicgroup.com");
    expect(screen.queryByRole("link", { name: "Evil" })).toBeNull();
    expect(screen.queryByText(/javascript/)).toBeNull();
  });
});
