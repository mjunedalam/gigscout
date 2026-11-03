import { arc, pie, type PieArcDatum } from "d3";
import { useMemo, useState } from "react";

import { compactNumber } from "../layout";
import { CHART_VARS } from "../palette";

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  color: string;
}

interface DonutProps {
  slices: DonutSlice[];
  size?: number;
  caption?: string;
}

/** Share of a whole, with the hovered slice's value in the centre. */
export function Donut({ slices, size = 200, caption = "total" }: DonutProps) {
  const [active, setActive] = useState<string | null>(null);
  const radius = size / 2;
  const arcs = useMemo(
    () => pie<DonutSlice>().value((d) => d.value).sort(null).padAngle(0.02)(slices.filter((s) => s.value > 0)),
    [slices],
  );
  const shape = arc<PieArcDatum<DonutSlice>>().innerRadius(radius * 0.64).outerRadius(radius - 4).cornerRadius(3);
  const grow = arc<PieArcDatum<DonutSlice>>().innerRadius(radius * 0.62).outerRadius(radius).cornerRadius(3);
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const shown = slices.find((s) => s.key === active);

  return (
    <svg width={size} height={size} role="img" aria-label={`Breakdown of ${compactNumber(total)} ${caption}`}>
      <g transform={`translate(${radius},${radius})`}>
        {arcs.length === 0 && <circle r={radius - 4} fill="none" stroke={CHART_VARS.grid} strokeWidth={radius * 0.36} />}
        {arcs.map((a) => (
          <path
            key={a.data.key}
            d={(a.data.key === active ? grow(a) : shape(a)) ?? ""}
            fill={a.data.color}
            opacity={active && a.data.key !== active ? 0.35 : 1}
            style={{ transition: "opacity 160ms ease" }}
            onMouseEnter={() => setActive(a.data.key)}
            onMouseLeave={() => setActive(null)}
          >
            <title>{`${a.data.label}: ${a.data.value}`}</title>
          </path>
        ))}
        <text textAnchor="middle" dy="-0.1em" className="gs-donut-value">
          {compactNumber(shown ? shown.value : total)}
        </text>
        <text textAnchor="middle" dy="1.5em" className="gs-axis">
          {shown ? shown.label : caption}
        </text>
      </g>
    </svg>
  );
}
