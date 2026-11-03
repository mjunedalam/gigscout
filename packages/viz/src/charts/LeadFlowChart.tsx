import type { LeadKind, TimeseriesRow } from "@gigscout/api-client";
import { LEAD_KINDS } from "@gigscout/api-client";
import { area, bisector, curveMonotoneX, scaleLinear, scaleUtc } from "d3";
import { type MouseEvent, useMemo, useState } from "react";

import { stackByKind, stackMax } from "../layout";
import { CHART_VARS, KIND_COLORS, KIND_LABELS } from "../palette";
import { ChartFrame, Tooltip } from "./ChartFrame";

const MARGIN = { top: 12, right: 12, bottom: 26, left: 34 };
const TOOLTIP_WIDTH = 180;

interface LeadFlowChartProps {
  rows: TimeseriesRow[];
  height?: number;
  kinds?: readonly LeadKind[];
}

interface Hover {
  index: number;
  x: number;
  width: number;
}

/** Stacked area of leads first seen per day, by kind. Hover for a per-day breakdown. */
export function LeadFlowChart({ rows, height = 240, kinds = LEAD_KINDS }: LeadFlowChartProps) {
  const series = useMemo(() => stackByKind(rows, kinds), [rows, kinds]);
  const dates = useMemo(() => rows.map((r) => new Date(`${r.date}T00:00:00Z`)), [rows]);
  const [hover, setHover] = useState<Hover | null>(null);
  const hovered = hover ? rows[hover.index] : undefined;

  const overlay = hover && hovered && (
    <Tooltip x={Math.min(MARGIN.left + hover.x + 12, MARGIN.left + hover.width - TOOLTIP_WIDTH)} y={MARGIN.top}>
      <strong>{dates[hover.index]!.toLocaleDateString("en", { dateStyle: "medium", timeZone: "UTC" })}</strong>
      {kinds.map((k) => (
        <div key={k} className="gs-tooltip-row">
          <span className="gs-dot" style={{ background: KIND_COLORS[k] }} />
          {KIND_LABELS[k]}
          <b>{hovered[k]}</b>
        </div>
      ))}
    </Tooltip>
  );

  return (
    <ChartFrame height={height} margin={MARGIN} label="Leads found per day, by kind" overlay={overlay}>
      {({ width, height: h }) => {
        if (!rows.length || width === 0) return null;
        const x = scaleUtc()
          .domain([dates[0]!, dates[dates.length - 1]!])
          .range([0, width]);
        const y = scaleLinear()
          .domain([0, Math.max(4, stackMax(series))])
          .nice()
          .range([h, 0]);
        const shape = area<[number, number]>()
          .x((_, i) => x(dates[i]!))
          .y0((d) => y(d[0]))
          .y1((d) => y(d[1]))
          .curve(curveMonotoneX);
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
                <text x={-8} dy="0.32em" textAnchor="end" className="gs-axis">
                  {t}
                </text>
              </g>
            ))}
            {x.ticks(Math.min(7, rows.length)).map((t) => (
              <text key={t.toISOString()} x={x(t)} y={h + 18} textAnchor="middle" className="gs-axis">
                {t.toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" })}
              </text>
            ))}
            {series.map((layer) => (
              <path
                key={layer.key}
                d={shape(layer as unknown as [number, number][]) ?? ""}
                fill={KIND_COLORS[layer.key]}
                fillOpacity={0.78}
                stroke={KIND_COLORS[layer.key]}
                strokeWidth={1}
                className="gs-fade-in"
              />
            ))}
            {hover && <line x1={hover.x} x2={hover.x} y2={h} stroke={CHART_VARS.strong} strokeOpacity={0.5} />}
            <rect width={width} height={h} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
          </>
        );
      }}
    </ChartFrame>
  );
}
