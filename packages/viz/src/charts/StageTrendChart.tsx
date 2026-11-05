import type { PipelineSeriesRow, PipelineStage } from "@gigscout/api-client";
import { bisector, curveMonotoneX, line, scaleLinear, scaleUtc } from "d3";
import { type MouseEvent, useMemo, useState } from "react";

import { CHART_VARS } from "../palette";
import { ChartFrame, Tooltip } from "./ChartFrame";

/** Pipeline steps keep one colour everywhere: cool at the top of the funnel, warm as a deal gets closer. */
export const STAGE_COLORS: Record<PipelineStage, string> = {
  found: "#7C8499",
  qualified: "#38BDF8",
  drafted: "#8B7CFF",
  sent: "#5AA9FF",
  replied: "#F5B544",
  proposal: "#C084FC",
  won: "#34D399",
  lost: "#FF6B6B",
};

const MARGIN = { top: 12, right: 14, bottom: 26, left: 34 };
const TOOLTIP_WIDTH = 170;

interface StageTrendChartProps {
  rows: PipelineSeriesRow[];
  stages: readonly PipelineStage[];
  labels: Record<string, string>;
  height?: number;
}

/** One line per pipeline step: how many leads reached it each day (or week). Hover for that day's numbers. */
export function StageTrendChart({ rows, stages, labels, height = 260 }: StageTrendChartProps) {
  const dates = useMemo(() => rows.map((r) => new Date(`${r.date}T00:00:00Z`)), [rows]);
  const top = useMemo(() => Math.max(4, ...rows.flatMap((r) => stages.map((s) => r[s]))), [rows, stages]);
  const [hover, setHover] = useState<{ index: number; x: number; width: number } | null>(null);
  const hovered = hover ? rows[hover.index] : undefined;

  const overlay = hover && hovered && (
    <Tooltip x={Math.min(MARGIN.left + hover.x + 12, MARGIN.left + hover.width - TOOLTIP_WIDTH)} y={MARGIN.top}>
      <strong>{dates[hover.index]!.toLocaleDateString("en", { dateStyle: "medium", timeZone: "UTC" })}</strong>
      {stages.map((s) => (
        <div key={s} className="gs-tooltip-row">
          <span className="gs-dot" style={{ background: STAGE_COLORS[s] }} />
          {labels[s] ?? s}
          <b>{hovered[s]}</b>
        </div>
      ))}
    </Tooltip>
  );

  return (
    <ChartFrame height={height} margin={MARGIN} label="Leads reaching each pipeline step over time" overlay={overlay}>
      {({ width, height: h }) => {
        if (rows.length < 2 || width === 0) return null;
        const x = scaleUtc().domain([dates[0]!, dates[dates.length - 1]!]).range([0, width]);
        const y = scaleLinear().domain([0, top]).nice().range([h, 0]);
        const path = (stage: PipelineStage) =>
          line<PipelineSeriesRow>().x((_, i) => x(dates[i]!)).y((r) => y(r[stage])).curve(curveMonotoneX)(rows) ?? "";
        const onMove = (event: MouseEvent<SVGRectElement>) => {
          const box = event.currentTarget.getBoundingClientRect();
          const index = bisector((d: Date) => d).center(dates, x.invert(event.clientX - box.left));
          setHover({ index, x: x(dates[index]!), width });
        };
        return (
          <>
            {y.ticks(4).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={width} stroke={CHART_VARS.grid} strokeDasharray="2 4" />
                <text x={-8} dy="0.32em" textAnchor="end" className="gs-axis">{t}</text>
              </g>
            ))}
            {x.ticks(Math.min(7, rows.length)).map((t) => (
              <text key={t.toISOString()} x={x(t)} y={h + 18} textAnchor="middle" className="gs-axis">
                {t.toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" })}
              </text>
            ))}
            {stages.map((s) => (
              <path key={s} d={path(s)} fill="none" stroke={STAGE_COLORS[s]} strokeWidth={2} className="gs-fade-in" />
            ))}
            {hover && (
              <>
                <line x1={hover.x} x2={hover.x} y2={h} stroke={CHART_VARS.strong} strokeOpacity={0.4} />
                {stages.map((s) => (
                  <circle key={s} cx={hover.x} cy={y(hovered![s])} r={3} fill={STAGE_COLORS[s]} />
                ))}
              </>
            )}
            <rect width={width} height={h} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
          </>
        );
      }}
    </ChartFrame>
  );
}
