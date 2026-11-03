import type { CSSProperties, ReactNode } from "react";

import { type Size, useSize } from "../useSize";

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface ChartFrameProps {
  height: number;
  margin: Margin;
  label: string;
  children: (inner: Size) => ReactNode;
  overlay?: ReactNode;
  style?: CSSProperties;
}

/** Measures its width, hands the inner drawing area to the chart, and keeps the SVG accessible. */
export function ChartFrame({ height, margin, label, children, overlay, style }: ChartFrameProps) {
  const [ref, size] = useSize<HTMLDivElement>();
  const inner = {
    width: Math.max(0, size.width - margin.left - margin.right),
    height: Math.max(0, height - margin.top - margin.bottom),
  };
  return (
    <div ref={ref} style={{ position: "relative", width: "100%", height, ...style }}>
      {size.width > 0 && (
        <svg width={size.width} height={height} role="img" aria-label={label} style={{ display: "block" }}>
          <g transform={`translate(${margin.left},${margin.top})`}>{children(inner)}</g>
        </svg>
      )}
      {overlay}
    </div>
  );
}

interface TooltipProps {
  x: number;
  y: number;
  children: ReactNode;
}

export function Tooltip({ x, y, children }: TooltipProps) {
  return (
    <div className="gs-tooltip" style={{ transform: `translate(${Math.round(x)}px, ${Math.round(y)}px)` }}>
      {children}
    </div>
  );
}
