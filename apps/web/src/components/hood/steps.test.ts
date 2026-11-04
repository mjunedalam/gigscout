import type { RunActivity } from "@gigscout/api-client";
import { describe, expect, it } from "vitest";

import { agentStates, toSteps } from "./steps";

const lead = { id: "a:1", title: "Django API", source: "a", budget: null };
const events: RunActivity[] = [
  { t: 0, kind: "stage", stage: "plan", agent: "head" },
  { t: 1, kind: "hood", n: 1, agent: "head", op: "tool", title: "Head of Sales handed the work to the Prospector", ms: 9000,
    detail: { tool: "delegate_to_scout" } },
  { t: 2, kind: "progress", agent: "prospector", stage: "search", done: 1, total: 4, label: "searching remotive" },
  { t: 3, kind: "hood", n: 2, agent: "prospector", op: "llm", title: "Prospector decided to search", ms: 1200,
    detail: { tokens_in: 100, tokens_out: 20 } },
  { t: 4, kind: "found", source: "remotive", leads: [lead] },
  { t: 5, kind: "reviewed", lead, score: 0.81, qualified: true, reason: null },
];

describe("agentStates", () => {
  it("marks the agent of the latest event as working while the run is live", () => {
    const s = agentStates(events, true);
    expect(s.qualifier.status).toBe("working");
    expect(s.prospector.status).toBe("done");
    expect(s.writer.status).toBe("waiting");
  });

  it("counts AI calls, tokens and progress, leaving hand-off time to the worker", () => {
    const s = agentStates(events, false);
    expect(s.prospector).toMatchObject({ aiCalls: 1, tokens: 120, busyMs: 1200, what: "searching remotive", progress: { done: 1, total: 4 } });
    expect(s.head).toMatchObject({ toolCalls: 1, busyMs: 0 });
    expect(s.qualifier.status).toBe("done");
  });
});

describe("toSteps", () => {
  it("turns events into plain sentences and keeps under-the-hood steps openable", () => {
    const steps = toSteps(events);
    expect(steps.map((s) => s.text)).toEqual([
      "Started planning the run",
      "Head of Sales handed the work to the Prospector",
      "Prospector decided to search",
      "Found 1 lead on remotive",
      'Qualified "Django API" · score 0.81',
    ]);
    expect(steps.filter((s) => s.hood).map((s) => s.hood?.n)).toEqual([1, 2]);
    expect(steps.at(-1)?.agent).toBe("qualifier");
  });
});
