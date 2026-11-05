import type { Outreach } from "@gigscout/api-client";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/render";
import { AGENT_AUTHOR, PitchEditor } from "./PitchEditor";

const DRAFT: Outreach = {
  id: 1, lead_id: "fake:1", channel: "email", to: "cto@client.com", subject: "Your Django API", body: "Hello there",
  status: "draft", source: "ai", kind: "first", run_id: "r1", created_by: AGENT_AUTHOR, created_at: "2026-11-05T10:00:00Z",
  sent_at: null, reviewed_by: null, reviewed_at: null, review_note: "",
};
const noop = () => undefined;

describe("pitch editor", () => {
  afterEach(cleanup);

  it("shows who drafted it and lets an approver send", () => {
    renderWithProviders(<PitchEditor draft={DRAFT} emailReady canApprove onDone={noop} />);
    expect(screen.getByText("by the agents")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Approve & send/ }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: /Reject/ }).hasAttribute("disabled")).toBe(false);
  });

  it("people who may not approve can only edit", () => {
    renderWithProviders(<PitchEditor draft={DRAFT} emailReady canApprove={false} onDone={noop} />);
    expect(screen.getByRole("button", { name: /Approve & send/ }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: /Reject/ }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: /Save draft/ }).hasAttribute("disabled")).toBe(false);
  });

  it("a marketplace bid is copied, then approved as posted", () => {
    renderWithProviders(<PitchEditor draft={{ ...DRAFT, channel: "bid", to: null, subject: "", kind: "follow_up" }}
      emailReady={false} canApprove leadUrl="https://example.com/job" onDone={noop} />);
    expect(screen.getByRole("link", { name: /Open listing/ }).getAttribute("href")).toBe("https://example.com/job");
    expect(screen.getByRole("button", { name: /Approve as posted/ }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByText("follow-up")).toBeTruthy();
  });
});
