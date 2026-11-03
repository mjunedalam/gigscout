import type { AgentKey, RunStage } from "@gigscout/api-client";

/** Agent identity colours, shared by the 3D line and the cockpit panels. */
export const AGENT_COLORS: Record<AgentKey, string> = {
  head: "#b7791f",
  prospector: "#1f9d55",
  qualifier: "#2f6fde",
  writer: "#7c4dcc",
};
export const AGENT_NAMES: Record<AgentKey, string> = {
  head: "Head of Sales",
  prospector: "Prospector",
  qualifier: "Qualifier",
  writer: "Outreach Writer",
};

export type StationKind = "brief" | "prospector" | "qualifier" | "writer" | "report";
export interface StationSpec {
  stage: RunStage;
  kind: StationKind;
  title: string;
  agent: AgentKey;
  /** Height of the machine's top, where its callout dot sits. */
  top: number;
}

export const STATIONS: readonly StationSpec[] = [
  { stage: "plan", kind: "brief", title: "Brief", agent: "head", top: 2.05 },
  { stage: "search", kind: "prospector", title: "Prospector", agent: "prospector", top: 3.0 },
  { stage: "qualify", kind: "qualifier", title: "Qualifier", agent: "qualifier", top: 2.35 },
  { stage: "write", kind: "writer", title: "Writer", agent: "writer", top: 2.25 },
  { stage: "report", kind: "report", title: "Report", agent: "head", top: 2.45 },
];

/** Station x positions along the line; everything else is placed relative to these. */
export const X = [-8.8, -4.4, 0, 4.4, 8.8] as const;
export const BELT = { z: 1.15, y: 0.37, x0: -6.3, x1: 10.7 } as const;
export const GROOVE_Z = 4.15;
export const TRAYS = {
  bin: { x: X[2] + 0.2, z: 3.0 },
  shortlist: { x: X[2] + 2.25, z: 3.0 },
  pitches: { x: X[4] - 1.0, z: 3.0 },
} as const;
/** The Head of Sales' control room: a mezzanine at the back, centred, overlooking every station. */
export const HQ = { x: 0, z: -5.4 } as const;
/** Scene bounds used to fit the overview camera. */
export const BOUNDS = { x0: X[0] - 2.4, x1: X[4] + 2.4, y0: 0, y1: 5.4, z0: -6.8, z1: GROOVE_Z + 0.3 } as const;
