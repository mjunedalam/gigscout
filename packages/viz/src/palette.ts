import type { LeadKind, LeadStatus, RunStatus } from "@gigscout/api-client";
import { interpolateRgb } from "d3";

/** Lead kinds carry meaning everywhere (badges, charts, the galaxy), so their colours are fixed tokens. */
export const KIND_COLORS: Record<LeadKind, string> = {
  project: "#8B7CFF",
  contract: "#2DD4BF",
  hiring: "#F5B544",
  inbound: "#FF6B8B",
};

export const KIND_LABELS: Record<LeadKind, string> = {
  project: "Client project",
  contract: "Contract",
  hiring: "Hiring signal",
  inbound: "Inbound",
};

export const STATUS_COLORS: Record<LeadStatus, string> = {
  new: "#7C8499",
  contacted: "#5AA9FF",
  proposal: "#8B7CFF",
  won: "#C6F432",
  lost: "#FF6B6B",
  archived: "#4A5063",
};

export const RUN_STATUS_COLORS: Record<RunStatus, string> = {
  queued: "#7C8499",
  running: "#5AA9FF",
  succeeded: "#C6F432",
  failed: "#FF6B6B",
  cancelled: "#4A5063",
};

const scoreRamp = interpolateRgb("#3B4256", "#C6F432");

/** Low scores fade into the surface, strong leads glow signal-lime. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#4A5063";
  return scoreRamp(Math.max(0, Math.min(1, score)));
}

/** Chart chrome reads CSS variables so light and dark themes restyle charts without re-rendering logic. */
export const CHART_VARS = {
  text: "var(--gs-text-muted)",
  grid: "var(--gs-line)",
  surface: "var(--gs-surface)",
  strong: "var(--gs-text)",
} as const;
