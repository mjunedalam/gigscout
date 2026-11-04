import type { AgentKey, HoodStep, RunActivity, RunStage } from "@gigscout/api-client";

export const AGENTS: AgentKey[] = ["head", "prospector", "qualifier", "writer"];

export const AGENT_ROLE: Record<AgentKey, string> = {
  head: "Plans the run and writes the briefing",
  prospector: "Searches lead sources",
  qualifier: "Judges each lead against the profile",
  writer: "Drafts the pitches",
};

const STAGE_TEXT: Record<RunStage, string> = {
  plan: "Started planning the run",
  search: "Started searching lead sources",
  qualify: "Started judging the leads",
  write: "Started drafting pitches",
  report: "Started writing the briefing",
};

export type AgentStatus = "waiting" | "working" | "done";

export interface AgentState {
  status: AgentStatus;
  /** What the agent is doing now, or last did. */
  what: string;
  progress: { done: number; total: number } | null;
  aiCalls: number;
  toolCalls: number;
  busyMs: number;
  tokens: number;
}

export interface Step {
  key: string;
  t: number;
  agent: AgentKey;
  text: string;
  tone: "neutral" | "good" | "bad";
  hood: HoodStep | null;
}

/** Which agent an event belongs to (found/reviewed/pitched carry no agent: they are always the same one). */
export function agentOf(e: RunActivity): AgentKey {
  switch (e.kind) {
    case "found":
      return "prospector";
    case "reviewed":
      return "qualifier";
    case "pitched":
      return "writer";
    default:
      return e.agent;
  }
}

/** Each agent's live state, folded from the run's events. */
export function agentStates(events: RunActivity[], active: boolean): Record<AgentKey, AgentState> {
  const states = Object.fromEntries(AGENTS.map((a) => [a, {
    status: "waiting", what: "", progress: null, aiCalls: 0, toolCalls: 0, busyMs: 0, tokens: 0,
  } satisfies AgentState])) as Record<AgentKey, AgentState>;
  let current: AgentKey | null = null;
  for (const e of events) {
    const agent = agentOf(e);
    const s = states[agent];
    current = agent;
    let next: AgentState = { ...s, status: "done" };
    if (e.kind === "progress") {
      next = { ...next, what: e.label || next.what, progress: e.total ? { done: e.done, total: e.total } : next.progress };
    } else if (e.kind === "act") {
      next = { ...next, what: e.what || next.what };
    } else if (e.kind === "hood") {
      next = {
        ...next,
        aiCalls: next.aiCalls + (e.op === "llm" ? 1 : 0),
        toolCalls: next.toolCalls + (e.op === "llm" ? 0 : 1),
        busyMs: next.busyMs + (e.detail.tool?.startsWith("delegate_") ? 0 : (e.ms ?? 0)), // a hand-off's time is the worker's
        tokens: next.tokens + (e.detail.tokens_in ?? 0) + (e.detail.tokens_out ?? 0),
      };
    }
    states[agent] = next;
  }
  if (active && current) states[current] = { ...states[current], status: "working" };
  return states;
}

/** The run as a readable timeline. Progress ticks are left out (the agent cards show them). */
export function toSteps(events: RunActivity[]): Step[] {
  const steps: Step[] = [];
  events.forEach((e, i) => {
    const base = { key: `${i}-${e.t}`, t: e.t, agent: agentOf(e), hood: null, tone: "neutral" as const };
    switch (e.kind) {
      case "stage":
        steps.push({ ...base, text: STAGE_TEXT[e.stage] });
        break;
      case "act":
        if (e.what) steps.push({ ...base, text: capitalize(e.what) });
        break;
      case "found":
        steps.push({ ...base, tone: e.leads.length ? "good" : "neutral",
          text: `Found ${e.leads.length} lead${e.leads.length === 1 ? "" : "s"} on ${e.source}` });
        break;
      case "reviewed":
        steps.push(e.qualified
          ? { ...base, tone: "good", text: `Qualified "${e.lead.title}" · score ${e.score.toFixed(2)}` }
          : { ...base, tone: "bad", text: `Dropped "${e.lead.title}"${e.reason ? ` · ${e.reason}` : ""}` });
        break;
      case "pitched":
        steps.push({ ...base, tone: "good", text: `Drafted a pitch for "${e.lead.title}"` });
        break;
      case "hood":
        steps.push({ ...base, tone: e.detail.error ? "bad" : "neutral", text: e.title, hood: e });
        break;
    }
  });
  return steps;
}

export function seconds(t: number): string {
  return t < 60 ? `${t.toFixed(1)}s` : `${Math.floor(t / 60)}m ${Math.round(t % 60)}s`;
}

export function millis(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
