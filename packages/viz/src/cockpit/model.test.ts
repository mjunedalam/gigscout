import type { ActivityLead, RunActivity } from "@gigscout/api-client";
import { describe, expect, it } from "vitest";

import { applyActivity, emptyCockpit, finishCockpit, isThinking, pileCounts, stageElapsed, stageProgress, stageState } from "./model";

const lead = (id: string, budget: number | null = 1000, source = "freelancer"): ActivityLead => ({ id, title: `Lead ${id}`, source, budget });
const run = (...events: RunActivity[]) => events.reduce(applyActivity, emptyCockpit());

describe("cockpit model", () => {
  it("tracks the current step and the order steps were first reached", () => {
    const m = run(
      { kind: "stage", t: 0, stage: "plan", agent: "head" },
      { kind: "stage", t: 1, stage: "search", agent: "prospector" },
      { kind: "stage", t: 5, stage: "plan", agent: "head" }, // a broadened run goes back
    );
    expect(m.stage).toBe("plan");
    expect(m.stagesSeen).toEqual(["plan", "search"]);
    expect(stageState(m, "search")).toBe("done");
    expect(stageState(m, "qualify")).toBe("pending");
  });

  it("counts found, reviewed, qualified and pitched leads and the money in the shortlist", () => {
    const m = run(
      { kind: "stage", t: 0, stage: "search", agent: "prospector" },
      { kind: "found", t: 1, source: "freelancer", leads: [lead("a", 5000), lead("b", 300), lead("c", null, "remoteok")] },
      { kind: "found", t: 2, source: "freelancer", leads: [lead("a", 5000)] }, // seen again: not double counted
      { kind: "reviewed", t: 3, lead: lead("a", 5000), score: 0.8, qualified: true, reason: null },
      { kind: "reviewed", t: 4, lead: lead("b", 300), score: 0.2, qualified: false, reason: "budget too low" },
      { kind: "pitched", t: 5, lead: lead("a", 5000) },
    );
    expect(m.order).toEqual(["a", "b", "c"]);
    expect(m.bySource).toEqual({ freelancer: 2, remoteok: 1 });
    expect(m.drops).toEqual({ "budget too low": 1 });
    expect(m.scores).toEqual([0.8, 0.2]);
    expect(m.value).toBe(5000);
    expect(pileCounts(m)).toEqual({ waiting: 1, dropped: 1, shortlisted: 0, pitched: 1 });
    expect(m.series.at(-1)).toMatchObject({ found: 3, scored: 2, qualified: 1 });
  });

  it("counts a lead once even when one search returns it for several queries", () => {
    const m = run({ kind: "found", t: 1, source: "remotive", leads: [lead("a", 900, "remotive"), lead("a", 900, "remotive"), lead("b", 900, "remotive")] });
    expect(m.order).toEqual(["a", "b"]);
    expect(m.bySource).toEqual({ remotive: 2 });
  });

  it("brings in leads reviewed from memory that were not found in this run", () => {
    const m = run({ kind: "reviewed", t: 1, lead: lead("old"), score: 0.7, qualified: true, reason: null });
    expect(m.leads.old).toMatchObject({ fromMemory: true, qualified: true });
    expect(m.bySource).toEqual({});
  });

  it("drops leads nobody reviewed when the run finishes", () => {
    const m = finishCockpit(
      run({ kind: "found", t: 1, source: "remotive", leads: [lead("x"), lead("y")] },
        { kind: "reviewed", t: 2, lead: lead("x"), score: 0.9, qualified: true, reason: null }),
      9,
    );
    expect(m.finished).toBe(true);
    expect(m.leads.y).toMatchObject({ qualified: false, reason: "not a match" });
    expect(m.drops).toEqual({ "not a match": 1 });
    expect(stageState(m, "report")).toBe("done");
  });

  it("leaves unreviewed leads waiting when the run was stopped, not dropped", () => {
    const m = finishCockpit(run({ kind: "found", t: 1, source: "remotive", leads: [lead("x", 900, "remotive")] }), 3, false);
    expect(m.finished).toBe(true);
    expect(pileCounts(m)).toMatchObject({ waiting: 1, dropped: 0 });
  });

  it("uses reported progress for the active step and shows what the agent is busy with", () => {
    const m = run(
      { kind: "stage", t: 0, stage: "search", agent: "prospector" },
      { kind: "progress", t: 1, agent: "prospector", stage: "search", done: 1, total: 4, label: "searched remotive" },
    );
    expect(stageProgress(m, "search")).toBe(0.25);
    expect(m.agents.prospector.what).toBe("searched remotive");
    expect(m.progress.search).toEqual({ done: 1, total: 4, label: "searched remotive" });
  });

  it("times each step: the active one keeps counting, finished ones keep their duration", () => {
    const m = run(
      { kind: "stage", t: 2, stage: "plan", agent: "head" },
      { kind: "stage", t: 12, stage: "search", agent: "prospector" },
      { kind: "stage", t: 20, stage: "plan", agent: "head" }, // broadened: plan again
    );
    expect(stageElapsed(m, "search", 30)).toBe(8);
    expect(stageElapsed(m, "plan", 25)).toBe(15); // 10s the first time + 5s so far
    expect(stageElapsed(finishCockpit(m, 26), "plan", 99)).toBe(16);
  });

  it("is thinking when the active step has been quiet for a while", () => {
    const m = run({ kind: "stage", t: 5, stage: "plan", agent: "head" });
    expect(isThinking(m, 6)).toBe(false);
    expect(isThinking(m, 9)).toBe(true);
    expect(isThinking(finishCockpit(m, 9), 20)).toBe(false);
  });

  it("counts each agent's actions and keeps a newest-first feed", () => {
    const m = run(
      { kind: "act", t: 0, agent: "prospector", what: "searched freelancer" },
      { kind: "act", t: 1, agent: "prospector", what: "searched remoteok" },
    );
    expect(m.agents.prospector).toEqual({ actions: 2, what: "searched remoteok" });
    expect(m.feed[0]!.text).toContain("remoteok");
  });

  it("fills each step's progress with its work and completes it once the run moves on", () => {
    const searching = run(
      { kind: "stage", t: 0, stage: "search", agent: "prospector" },
      { kind: "found", t: 1, source: "freelancer", leads: [lead("a"), lead("b")] },
    );
    const p = stageProgress(searching, "search");
    expect(p).toBeGreaterThan(0);
    expect(p).toBeLessThan(1);
    const moved = applyActivity(searching, { kind: "stage", t: 2, stage: "qualify", agent: "qualifier" });
    expect(stageProgress(moved, "search")).toBe(1);
    expect(stageProgress(moved, "write")).toBe(0);
  });
});
