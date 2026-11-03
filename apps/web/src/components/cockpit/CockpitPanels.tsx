import type { AgentKey, Run } from "@gigscout/api-client";
import {
  AGENT_COLORS, AGENT_NAMES, BarList, type CockpitModel, LeadsOverTime, NOT_A_MATCH, pileCounts, ScoreHistogram,
  Sparkline, STAGE_AGENT, stageProgress, stageState, type StageState, STAGES,
} from "@gigscout/viz";
import type { CSSProperties, ReactNode } from "react";

const DROP_REASONS = ["budget too low", "off-stack", "too many bids", "red flags", "low fit", NOT_A_MATCH];
const SOURCE_COLOR = AGENT_COLORS.prospector;
const DROP_COLOR = "#9aa1ab";
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

// ------------------------------------------------------------------ top: KPI strip

export function KpiStrip({ model, run, controls }: { model: CockpitModel; run: Run | null; controls: ReactNode }) {
  const found = model.series.at(-1)?.found ?? 0;
  const scored = model.scores.length;
  const qualified = model.series.at(-1)?.qualified ?? 0;
  const counts = pileCounts(model);
  const trend = (k: "found" | "scored" | "qualified") => model.series.map((p) => p[k]);
  const tiles: { label: string; value: string; spark?: number[]; color?: string }[] = [
    { label: "Leads found", value: String(found), spark: trend("found"), color: AGENT_COLORS.prospector },
    { label: "Reviewed", value: String(scored), spark: trend("scored"), color: AGENT_COLORS.qualifier },
    { label: "Qualified", value: String(qualified), spark: trend("qualified"), color: AGENT_COLORS.writer },
    { label: "Qualify rate", value: scored ? `${Math.round((qualified / scored) * 100)}%` : "–" },
    { label: "Pipeline value", value: money.format(model.value) },
    { label: "Pitches", value: `${counts.pitched}/3` },
    { label: "Run time", value: clock(model.t), },
  ];
  return (
    <section className="gs-panel gs-cockpit-kpis" aria-label="Run totals">
      {tiles.map((tile) => (
        <div key={tile.label} className="gs-cockpit-kpi">
          <span className="gs-eyebrow">{tile.label}</span>
          <div className="v">{tile.value}</div>
          {tile.spark ? <Sparkline values={tile.spark} width={140} height={20} color={tile.color} label={`${tile.label} trend`} /> : <div className="d">{tile.label === "Run time" && run ? run.profile_name : " "}</div>}
        </div>
      ))}
      <div className="gs-cockpit-ctrls">{controls}</div>
    </section>
  );
}

// ------------------------------------------------------------------ left: agents and feed

const AGENTS: AgentKey[] = ["head", "prospector", "qualifier", "writer"];

function agentState(model: CockpitModel, agent: AgentKey): StageState {
  const states = STAGES.filter((s) => STAGE_AGENT[s] === agent).map((s) => stageState(model, s));
  if (states.includes("active")) return "active";
  if (agent === "head" && model.stagesSeen.length && !model.finished) return "active"; // directs every step
  return states.includes("done") ? "done" : "pending";
}

function agentProgress(model: CockpitModel, agent: AgentKey): number {
  const stages = STAGES.filter((s) => STAGE_AGENT[s] === agent);
  if (agent === "head") return model.finished ? 1 : model.stagesSeen.length / STAGES.length;
  return Math.max(...stages.map((s) => stageProgress(model, s)));
}

export function AgentCards({ model }: { model: CockpitModel }) {
  return (
    <div className="gs-panel gs-cockpit-agents" aria-label="Agents on this run">
      <span className="gs-eyebrow">Agents on this run</span>
      {AGENTS.map((agent) => {
        const state = agentState(model, agent);
        const { actions, what } = model.agents[agent];
        return (
          <div key={agent} className="gs-cockpit-agent" data-state={state} style={{ "--c": AGENT_COLORS[agent] } as CSSProperties}>
            <div className="top">
              <span className="sw" />
              {AGENT_NAMES[agent]}
              <span className="chip">{state === "active" ? "working" : state === "done" ? "✓ done" : "waiting"}</span>
            </div>
            <div className="task">{what || (state === "pending" ? "not needed yet" : "…")}</div>
            <div className="bar"><i style={{ width: `${Math.round(agentProgress(model, agent) * 100)}%` }} /></div>
            <div className="meta">{actions} {actions === 1 ? "action" : "actions"}</div>
          </div>
        );
      })}
    </div>
  );
}

export function LiveFeed({ model }: { model: CockpitModel }) {
  return (
    <div className="gs-panel gs-cockpit-feed">
      <span className="gs-eyebrow">Live feed</span>
      <ul aria-live="polite">
        {model.feed.map((item, i) => (
          <li key={`${item.t}-${i}-${item.text}`}>
            <time>{clock(item.t)}</time>
            <span style={{ color: AGENT_COLORS[item.agent] }}>{item.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------ right: charts

export function CockpitCharts({ model }: { model: CockpitModel }) {
  const bins = Array.from({ length: 10 }, (_, i) => ({
    from: i / 10, to: (i + 1) / 10,
    count: model.scores.filter((s) => s >= i / 10 && (i === 9 ? s <= 1 : s < (i + 1) / 10)).length,
  }));
  const sources = Object.entries(model.bySource).sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <aside className="gs-cockpit-charts" aria-label="Run charts">
      <div className="gs-panel gs-cockpit-chart">
        <span className="gs-eyebrow">Leads over time</span>
        <div className="gs-cockpit-legend">
          <span><i style={{ background: AGENT_COLORS.prospector }} />found</span>
          <span><i style={{ background: AGENT_COLORS.qualifier }} />reviewed</span>
          <span><i style={{ background: AGENT_COLORS.writer }} />qualified</span>
        </div>
        <LeadsOverTime series={model.series} height={130}
          colors={{ found: AGENT_COLORS.prospector, scored: AGENT_COLORS.qualifier, qualified: AGENT_COLORS.writer }} />
      </div>
      <div className="gs-panel gs-cockpit-chart">
        <span className="gs-eyebrow">Found by source</span>
        <BarList label="Leads found per source" height={110}
          rows={(sources.length ? sources : [["no leads yet", 0] as [string, number]]).map(([label, value]) => ({ label, value, color: SOURCE_COLOR }))} />
      </div>
      <div className="gs-panel gs-cockpit-chart">
        <span className="gs-eyebrow">Fit score distribution</span>
        <ScoreHistogram bins={bins} height={120} />
      </div>
      <div className="gs-panel gs-cockpit-chart">
        <span className="gs-eyebrow">Why leads were dropped</span>
        <BarList label="Dropped leads by reason" height={120}
          rows={DROP_REASONS.map((label) => ({ label, value: model.drops[label] ?? 0, color: DROP_COLOR }))} />
      </div>
    </aside>
  );
}
