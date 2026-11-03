import { scaleBand, scaleLinear } from "d3";

import { CHART_VARS, scoreColor } from "../palette";
import { ChartFrame } from "./ChartFrame";

const MARGIN = { top: 16, right: 8, bottom: 26, left: 30 };

interface ScoreHistogramProps {
  bins: { from: number; to: number; count: number }[];
  threshold?: number;
  height?: number;
}

/** How qualification scores are distributed; bars are tinted by the score they represent. */
export function ScoreHistogram({ bins, threshold = 0.6, height = 220 }: ScoreHistogramProps) {
  return (
    <ChartFrame height={height} margin={MARGIN} label="Distribution of lead scores">
      {({ width, height: h }) => {
        const x = scaleBand<number>()
          .domain(bins.map((b) => b.from))
          .range([0, width])
          .padding(0.18);
        const y = scaleLinear()
          .domain([0, Math.max(1, ...bins.map((b) => b.count))])
          .nice()
          .range([h, 0]);
        const thresholdX = (threshold / 1) * width;
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
            {bins.map((b, i) => (
              <g key={b.from} className="gs-rise" style={{ animationDelay: `${i * 30}ms` }}>
                <rect
                  x={x(b.from)}
                  y={y(b.count)}
                  width={x.bandwidth()}
                  height={h - y(b.count)}
                  rx={3}
                  fill={scoreColor((b.from + b.to) / 2)}
                >
                  <title>{`${b.from.toFixed(1)}–${b.to.toFixed(1)}: ${b.count} leads`}</title>
                </rect>
                <text x={(x(b.from) ?? 0) + x.bandwidth() / 2} y={h + 18} textAnchor="middle" className="gs-axis">
                  {b.from.toFixed(1)}
                </text>
              </g>
            ))}
            <line x1={thresholdX} x2={thresholdX} y2={h} stroke="var(--gs-signal)" strokeDasharray="4 3" />
            <text x={thresholdX + 6} y={8} className="gs-axis gs-axis-signal">
              qualified ≥ {threshold}
            </text>
          </>
        );
      }}
    </ChartFrame>
  );
}
