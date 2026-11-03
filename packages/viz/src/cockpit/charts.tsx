import { curveMonotoneX, line, scaleBand, scaleLinear } from "d3";

import { ChartFrame } from "../charts/ChartFrame";
import { CHART_VARS } from "../palette";
import type { SeriesPoint } from "./model";

const LINE_MARGIN = { top: 8, right: 8, bottom: 20, left: 28 };

export interface LeadsOverTimeProps {
  series: SeriesPoint[];
  colors: { found: string; scored: string; qualified: string };
  height?: number;
}

/** Found, reviewed and qualified leads over the run, as three cumulative lines. */
export function LeadsOverTime({ series, colors, height = 150 }: LeadsOverTimeProps) {
  const end = Math.max(series.at(-1)?.t ?? 0, 1);
  const top = Math.max(10, ...series.map((p) => p.found));
  return (
    <ChartFrame height={height} margin={LINE_MARGIN} label="Leads found, reviewed and qualified over the run">
      {({ width, height: h }) => {
        const x = scaleLinear([0, end], [0, width]);
        const y = scaleLinear([0, top], [h, 0]).nice();
        const path = (key: keyof Omit<SeriesPoint, "t">) =>
          line<SeriesPoint>().x((p) => x(p.t)).y((p) => y(p[key])).curve(curveMonotoneX)(series) ?? "";
        return (
          <>
            {y.ticks(3).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={width} stroke={CHART_VARS.grid} />
                <text x={-6} dy="0.32em" textAnchor="end" fontSize={10} fill={CHART_VARS.text}>{t}</text>
              </g>
            ))}
            {x.ticks(4).map((t) => (
              <text key={t} x={x(t)} y={h + 14} textAnchor="middle" fontSize={10} fill={CHART_VARS.text}>{formatSeconds(t)}</text>
            ))}
            {(["found", "scored", "qualified"] as const).map((k) => (
              <path key={k} d={path(k)} fill="none" stroke={colors[k]} strokeWidth={2} />
            ))}
          </>
        );
      }}
    </ChartFrame>
  );
}

export interface BarRow {
  label: string;
  value: number;
  color: string;
}

const BAR_MARGIN = { top: 2, right: 26, bottom: 2, left: 96 };

/** Labelled horizontal bars with the value at the end of each bar. */
export function BarList({ rows, height = 110, label }: { rows: BarRow[]; height?: number; label: string }) {
  const top = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ChartFrame height={height} margin={BAR_MARGIN} label={label}>
      {({ width, height: h }) => {
        const y = scaleBand(rows.map((r) => r.label), [0, h]).padding(0.28);
        const x = scaleLinear([0, top], [0, width]);
        return rows.map((r) => (
          <g key={r.label} transform={`translate(0,${y(r.label)})`}>
            <text x={-8} y={y.bandwidth() / 2} dy="0.35em" textAnchor="end" fontSize={11} fill={CHART_VARS.text}>{r.label}</text>
            <rect width={Math.max(x(r.value), r.value ? 2 : 0)} height={y.bandwidth()} rx={3} fill={r.color} style={{ transition: "width .3s" }} />
            <text x={x(r.value) + 5} y={y.bandwidth() / 2} dy="0.35em" fontSize={11} fontWeight={700} fill={CHART_VARS.strong}>{r.value}</text>
          </g>
        ));
      }}
    </ChartFrame>
  );
}

function formatSeconds(t: number): string {
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}
