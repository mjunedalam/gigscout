import type { MapPoint } from "@gigscout/api-client";
import { KIND_COLORS, KIND_LABELS } from "@gigscout/viz";
import { useMemo, useState } from "react";

interface FlatGalaxyProps {
  points: MapPoint[];
  height: number;
  onSelect: (id: string) => void;
}

const VIEW = 1000;
const PAD = 40;

function project(points: MapPoint[]) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const span = (lo: number, hi: number) => (hi - lo || 1);
  return points.map((p) => ({
    point: p,
    cx: PAD + ((p.x - minX) / span(minX, maxX)) * (VIEW - PAD * 2),
    cy: PAD + ((p.y - minY) / span(minY, maxY)) * (VIEW - PAD * 2),
    r: 4 + (p.score ?? 0) * 7,
  }));
}

/** The lead galaxy as a flat 2D map, for browsers without WebGL. Same meaning layout, same colours, still clickable. */
export function FlatGalaxy({ points, height, onSelect }: FlatGalaxyProps) {
  const dots = useMemo(() => project(points), [points]);
  const [hover, setHover] = useState<MapPoint | null>(null);

  return (
    <div className="gs-galaxy gs-flat-galaxy" style={{ height, position: "relative" }}>
      <svg viewBox={`0 0 ${VIEW} ${VIEW}`} preserveAspectRatio="xMidYMid meet" width="100%" height="100%" role="group" aria-label="Leads clustered by meaning">
        {dots.map(({ point, cx, cy, r }) => (
          <circle
            key={point.id}
            cx={cx}
            cy={cy}
            r={r}
            fill={KIND_COLORS[point.kind]}
            className="gs-flat-dot"
            role="button"
            tabIndex={0}
            aria-label={`${point.title}, ${KIND_LABELS[point.kind]}${point.score === null ? "" : `, score ${Math.round(point.score * 100)}`}`}
            onClick={() => onSelect(point.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(point.id);
              }
            }}
            onPointerEnter={() => setHover(point)}
            onPointerLeave={() => setHover(null)}
            onFocus={() => setHover(point)}
            onBlur={() => setHover(null)}
          />
        ))}
      </svg>
      {hover && (
        <div className="gs-tooltip" style={{ top: 12, left: 12 }}>
          <strong>{hover.title}</strong>
          <div className="gs-tooltip-row">
            <span className="gs-dot" style={{ background: KIND_COLORS[hover.kind] }} />
            {KIND_LABELS[hover.kind]}
            <b>{hover.score === null ? "–" : Math.round(hover.score * 100)}</b>
          </div>
        </div>
      )}
    </div>
  );
}
