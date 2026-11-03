import type { Analytics } from "@gigscout/api-client";
import { line, scaleBand, scaleLinear } from "d3";

import { CHART_VARS, RUN_STATUS_COLORS } from "../palette";
import { ChartFrame } from "./ChartFrame";

const MARGIN = { top: 14, right: 40, bottom: 24, left: 40 };

interface RunTimelineProps {
  runs: Analytics["runs"];
  height?: number;
  onSelect?: (id: string) => void;
}

/** Bars: run duration, coloured by outcome. Line: new leads each run brought in (right axis). */
export function RunTimeline({ runs, height = 220, onSelect }: RunTimelineProps) {
  return (
    <ChartFrame height={height} margin={MARGIN} label="Recent runs: duration and new leads">
      {({ width, height: h }) => {
        const x = scaleBand<string>()
          .domain(runs.map((r) => r.id))
          .range([0, width])
          .padding(0.25);
        const yTime = scaleLinear()
          .domain([0, Math.max(10, ...runs.map((r) => r.duration_seconds ?? 0))])
          .nice()
          .range([h, 0]);
        const yNew = scaleLinear()
          .domain([0, Math.max(5, ...runs.map((r) => r.new))])
          .nice()
          .range([h, 0]);
        const center = (id: string) => (x(id) ?? 0) + x.bandwidth() / 2;
        const path = line<Analytics["runs"][number]>()
          .x((r) => center(r.id))
          .y((r) => yNew(r.new))(runs);
        return (
          <>
            {yTime.ticks(4).map((t) => (
              <g key={t} transform={`translate(0,${yTime(t)})`}>
                <line x2={width} stroke={CHART_VARS.grid} strokeDasharray="2 4" />
                <text x={-8} dy="0.32em" textAnchor="end" className="gs-axis">
                  {t}s
                </text>
              </g>
            ))}
            {yNew.ticks(4).map((t) => (
              <text key={t} x={width + 8} y={yNew(t)} dy="0.32em" className="gs-axis">
                {t}
              </text>
            ))}
            {runs.map((r, i) => (
              <rect
                key={r.id}
                x={x(r.id)}
                y={yTime(r.duration_seconds ?? 0)}
                width={x.bandwidth()}
                height={h - yTime(r.duration_seconds ?? 0)}
                rx={2}
                fill={RUN_STATUS_COLORS[r.status]}
                fillOpacity={0.55}
                className="gs-rise"
                style={{ animationDelay: `${i * 20}ms`, cursor: onSelect ? "pointer" : "default" }}
                onClick={() => onSelect?.(r.id)}
              >
                <title>{`${new Date(r.at).toLocaleString()} · ${r.status} · ${r.duration_seconds ?? "?"}s · ${r.new} new`}</title>
              </rect>
            ))}
            {path && <path d={path} fill="none" stroke="var(--gs-text)" strokeWidth={1.5} className="gs-draw" />}
            {runs.map((r) => (
              <circle key={r.id} cx={center(r.id)} cy={yNew(r.new)} r={2.5} fill="var(--gs-text)" />
            ))}
            <text x={0} y={h + 18} className="gs-axis">
              older
            </text>
            <text x={width} y={h + 18} textAnchor="end" className="gs-axis">
              latest
            </text>
          </>
        );
      }}
    </ChartFrame>
  );
}
