import type { Analytics } from "@gigscout/api-client";
import { scaleLog, scaleSqrt, scaleSymlog } from "d3";
import { useState } from "react";

import { compactNumber } from "../layout";
import { CHART_VARS, KIND_COLORS } from "../palette";
import { ChartFrame, Tooltip } from "./ChartFrame";

const MARGIN = { top: 16, right: 16, bottom: 34, left: 52 };

type Point = Analytics["competition"][number];

interface CompetitionScatterProps {
  points: Point[];
  height?: number;
  onSelect?: (id: string) => void;
}

/**
 * Budget against competing bids. The sweet spot for an agency is top-left: big budgets, few rivals.
 * Dot size is the lead's score.
 */
export function CompetitionScatter({ points, height = 300, onSelect }: CompetitionScatterProps) {
  const [hover, setHover] = useState<{ point: Point; x: number; y: number } | null>(null);
  const overlay = hover && (
    <Tooltip x={hover.x + MARGIN.left + 14} y={hover.y + MARGIN.top - 10}>
      <strong>{hover.point.title}</strong>
      <div className="gs-tooltip-row">
        Budget <b>${compactNumber(hover.point.budget_usd)}</b>
      </div>
      <div className="gs-tooltip-row">
        Bids <b>{hover.point.bids}</b>
      </div>
      {hover.point.score !== null && (
        <div className="gs-tooltip-row">
          Score <b>{hover.point.score.toFixed(2)}</b>
        </div>
      )}
    </Tooltip>
  );

  return (
    <ChartFrame height={height} margin={MARGIN} label="Lead budget against competing bids" overlay={overlay}>
      {({ width, height: h }) => {
        const maxBids = Math.max(10, ...points.map((p) => p.bids));
        const budgets = points.map((p) => p.budget_usd);
        const x = scaleSymlog().domain([0, maxBids]).range([0, width]).nice();
        const y = scaleLog()
          .domain([Math.max(10, Math.min(...budgets, 100)), Math.max(1000, ...budgets)])
          .range([h, 0])
          .nice()
          .clamp(true);
        const r = scaleSqrt().domain([0, 1]).range([3, 11]);
        return (
          <>
            <rect width={width * 0.25} height={h * 0.4} fill="var(--gs-signal)" opacity={0.06} rx={6} />
            <text x={8} y={16} className="gs-axis gs-axis-signal">
              sweet spot
            </text>
            {y.ticks(4).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={width} stroke={CHART_VARS.grid} strokeDasharray="2 4" />
                <text x={-8} dy="0.32em" textAnchor="end" className="gs-axis">
                  ${compactNumber(t)}
                </text>
              </g>
            ))}
            {x.ticks(6).map((t) => (
              <text key={t} x={x(t)} y={h + 18} textAnchor="middle" className="gs-axis">
                {t}
              </text>
            ))}
            <text x={width} y={h + 32} textAnchor="end" className="gs-axis">
              competing bids →
            </text>
            {points.map((p) => (
              <circle
                key={p.id}
                cx={x(p.bids)}
                cy={y(p.budget_usd)}
                r={r(p.score ?? 0.2)}
                fill={KIND_COLORS[p.kind]}
                fillOpacity={hover?.point.id === p.id ? 1 : 0.62}
                stroke={hover?.point.id === p.id ? CHART_VARS.strong : "none"}
                style={{ cursor: onSelect ? "pointer" : "default", transition: "fill-opacity 120ms" }}
                onMouseEnter={() => setHover({ point: p, x: x(p.bids), y: y(p.budget_usd) })}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelect?.(p.id)}
              />
            ))}
          </>
        );
      }}
    </ChartFrame>
  );
}
