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

describe("grounding", () => {
  afterEach(cleanup);

  it("shows the documents a pitch cites and the claims they do not back", () => {
    const grounded: Outreach = {
      ...DRAFT,
      evidence: [{ doc_id: 1, title: "Clinic booking MVP", kind: "case_study", similarity: 0.8, excerpt: "We built" }],
      claims: [
        { sentence: "We built a booking app for clinics.", supported: true, source: "Clinic booking MVP", similarity: 0.8 },
        { sentence: "We have 40 Fortune 500 clients.", supported: false, source: null, similarity: 0.1 },
      ],
    };
    renderWithProviders(<PitchEditor draft={grounded} emailReady canApprove onDone={noop} />);
    expect(screen.getByText("Clinic booking MVP")).toBeTruthy();
    expect(screen.getByText("1 claim backed")).toBeTruthy();
    expect(screen.getByText("1 not in your documents")).toBeTruthy();
    expect(screen.getByText("We have 40 Fortune 500 clients.")).toBeTruthy();
  });

  it("without documents it points to the knowledge base", () => {
    renderWithProviders(<PitchEditor draft={DRAFT} emailReady canApprove onDone={noop} />);
    expect(screen.getByRole("link", { name: "knowledge base" })).toBeTruthy();
  });
});
