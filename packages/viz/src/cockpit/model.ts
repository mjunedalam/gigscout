import type { ActivityLead, AgentKey, RunActivity, RunStage } from "@gigscout/api-client";

/**
 * The cockpit's view of one run, folded from structured run activity. Pure and immutable: the page derives
 * its panels from it and the 3D production line reads it every frame.
 */
export const STAGES: readonly RunStage[] = ["plan", "search", "qualify", "write", "report"];
export const STAGE_AGENT: Record<RunStage, AgentKey> = {
  plan: "head", search: "prospector", qualify: "qualifier", write: "writer", report: "head",
};
export const NOT_A_MATCH = "not a match";
const FEED_SIZE = 40;
const PITCHES = 3;

export interface CockpitLead extends ActivityLead {
  fromMemory: boolean; // reviewed this run but found in an earlier one
  found: boolean;
  reviewed: boolean;
  qualified: boolean;
  pitched: boolean;
  score: number | null;
  reason: string | null;
}

export interface FeedItem {
  t: number;
  agent: AgentKey;
  text: string;
}

export interface SeriesPoint {
  t: number;
  found: number;
  scored: number;
  qualified: number;
}

export interface CockpitModel {
  stage: RunStage | null;
  stagesSeen: RunStage[];
  finished: boolean;
  t: number;
  leads: Record<string, CockpitLead>;
  order: string[];
  agents: Record<AgentKey, { actions: number; what: string }>;
  feed: FeedItem[];
  series: SeriesPoint[];
  bySource: Record<string, number>;
  drops: Record<string, number>;
  scores: number[];
  value: number;
  stageWork: Record<RunStage, number>;
}

const idleAgent = () => ({ actions: 0, what: "" });

export function emptyCockpit(): CockpitModel {
  return {
    stage: null, stagesSeen: [], finished: false, t: 0, leads: {}, order: [],
    agents: { head: idleAgent(), prospector: idleAgent(), qualifier: idleAgent(), writer: idleAgent() },
    feed: [], series: [], bySource: {}, drops: {}, scores: [], value: 0,
    stageWork: { plan: 0, search: 0, qualify: 0, write: 0, report: 0 },
  };
}

export function applyActivity(m: CockpitModel, e: RunActivity): CockpitModel {
  const next = { ...m, t: Math.max(m.t, e.t) };
  switch (e.kind) {
    case "stage":
      return {
        ...next, stage: e.stage,
        stagesSeen: m.stagesSeen.includes(e.stage) ? m.stagesSeen : [...m.stagesSeen, e.stage],
      };
    case "act":
      return {
        ...next,
        agents: { ...m.agents, [e.agent]: { actions: m.agents[e.agent].actions + 1, what: e.what } },
        stageWork: m.stage ? { ...m.stageWork, [m.stage]: m.stageWork[m.stage] + 1 } : m.stageWork,
        feed: pushFeed(m.feed, { t: e.t, agent: e.agent, text: capitalize(e.what) }),
      };
    case "found":
      return withSeries(found(next, e.source, e.leads, e.t));
    case "reviewed":
      return withSeries(reviewed(next, e.lead, e.score, e.qualified, e.reason, e.t));
    case "pitched": {
      const current = m.leads[e.lead.id] ?? newLead(e.lead, true);
      return {
        ...next,
        leads: { ...m.leads, [e.lead.id]: { ...current, pitched: true } },
        order: m.order.includes(e.lead.id) ? m.order : [...m.order, e.lead.id],
        feed: pushFeed(m.feed, { t: e.t, agent: "writer", text: `Pitch drafted for "${e.lead.title}"` }),
      };
    }
  }
}

/**
 * The run ended. If it completed, leads nobody reviewed were not close enough to the agency profile to be looked
 * at; if it was stopped, they simply stay waiting.
 */
export function finishCockpit(m: CockpitModel, t: number, completed = true): CockpitModel {
  let next: CockpitModel = { ...m, finished: true, stage: null, t: Math.max(m.t, t) };
  for (const id of completed ? m.order : []) {
    const lead = next.leads[id]!;
    if (!lead.reviewed) next = reviewed(next, lead, null, false, NOT_A_MATCH, t, false);
  }
  return withSeries({ ...next, stagesSeen: next.stagesSeen.includes("report") ? next.stagesSeen : [...next.stagesSeen, "report"] });
}

export type StageState = "pending" | "active" | "done";

export function stageState(m: CockpitModel, stage: RunStage): StageState {
  if (m.stage === stage) return "active";
  return m.stagesSeen.includes(stage) ? "done" : "pending";
}

/** 0..1 for each step: completed steps are full; the active one fills with its work, never quite reaching 1. */
export function stageProgress(m: CockpitModel, stage: RunStage): number {
  const state = stageState(m, stage);
  if (state !== "active") return state === "done" ? 1 : 0;
  const counts = pileCounts(m);
  const found = m.order.filter((id) => m.leads[id]!.found).length;
  const scored = m.scores.length;
  const work: Record<RunStage, number> = {
    plan: 1 - Math.exp(-(m.stageWork.plan + 1) / 2),
    search: 1 - Math.exp(-found / 25),
    qualify: Math.max(found ? scored / found : 0, 1 - Math.exp(-scored / 8)),
    write: counts.pitched / PITCHES,
    report: 1 - Math.exp(-(m.stageWork.report + 1) / 2),
  };
  return Math.min(Math.max(work[stage], 0.04), 0.95);
}

export interface PileCounts {
  waiting: number;
  dropped: number;
  shortlisted: number;
  pitched: number;
}

export function pileCounts(m: CockpitModel): PileCounts {
  const counts = { waiting: 0, dropped: 0, shortlisted: 0, pitched: 0 };
  for (const id of m.order) {
    const l = m.leads[id]!;
    if (l.pitched) counts.pitched++;
    else if (!l.reviewed) counts.waiting++;
    else if (l.qualified) counts.shortlisted++;
    else counts.dropped++;
  }
  return counts;
}

function found(m: CockpitModel, source: string, leads: ActivityLead[], t: number): CockpitModel {
  const unique = [...new Map(leads.map((l) => [l.id, l])).values()]; // one search can return a lead per query
  const fresh = unique.filter((l) => !m.leads[l.id]);
  if (!fresh.length) return m;
  const added = Object.fromEntries(fresh.map((l) => [l.id, newLead(l, false)]));
  const bySource = { ...m.bySource };
  for (const l of fresh) bySource[l.source] = (bySource[l.source] ?? 0) + 1;
  return {
    ...m,
    leads: { ...m.leads, ...added },
    order: [...m.order, ...fresh.map((l) => l.id)],
    bySource,
    feed: pushFeed(m.feed, { t, agent: "prospector", text: `${fresh.length} new on ${source}` }),
  };
}

function reviewed(
  m: CockpitModel, lead: ActivityLead, score: number | null, qualified: boolean, reason: string | null, t: number,
  announce = true,
): CockpitModel {
  const current = m.leads[lead.id] ?? newLead(lead, true);
  if (current.reviewed && (current.qualified || !qualified)) return m; // first verdict wins unless later qualified
  const upgrade = current.reviewed && !current.qualified && qualified;
  const drops = { ...m.drops };
  if (upgrade && current.reason) drops[current.reason] = Math.max((drops[current.reason] ?? 1) - 1, 0);
  if (!qualified && reason) drops[reason] = (drops[reason] ?? 0) + 1;
  const text = qualified
    ? `✓ "${lead.title}"${score !== null ? ` ${score.toFixed(2)}` : ""}`
    : `✗ "${lead.title}" (${reason ?? "dropped"})`;
  return {
    ...m,
    leads: { ...m.leads, [lead.id]: { ...current, reviewed: true, qualified, score, reason } },
    order: m.order.includes(lead.id) ? m.order : [...m.order, lead.id],
    drops,
    scores: score !== null && !current.reviewed ? [...m.scores, score] : m.scores,
    value: qualified ? m.value + (lead.budget ?? 0) : m.value,
    feed: announce && (qualified || m.scores.length % 5 === 0) ? pushFeed(m.feed, { t, agent: "qualifier", text }) : m.feed,
  };
}

function newLead(lead: ActivityLead, fromMemory: boolean): CockpitLead {
  return { ...lead, fromMemory, found: !fromMemory, reviewed: false, qualified: false, pitched: false, score: null, reason: null };
}

function withSeries(m: CockpitModel): CockpitModel {
  const found = m.order.filter((id) => m.leads[id]!.found).length;
  const point = { t: m.t, found, scored: m.scores.length, qualified: m.order.filter((id) => m.leads[id]!.qualified).length };
  const last = m.series.at(-1);
  if (last && last.found === point.found && last.scored === point.scored && last.qualified === point.qualified) return m;
  return { ...m, series: [...m.series, point] };
}

function pushFeed(feed: FeedItem[], item: FeedItem): FeedItem[] {
  return [item, ...feed].slice(0, FEED_SIZE);
}

const capitalize = (s: string) => (s ? s[0]!.toUpperCase() + s.slice(1) : s);
