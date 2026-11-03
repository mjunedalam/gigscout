import { area, curveMonotoneX, line, scaleLinear } from "d3";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  label: string;
}

/** A tiny trend line for live metric tiles; the latest point is marked. */
export function Sparkline({ values, width = 120, height = 32, color = "var(--gs-signal)", label }: SparklineProps) {
  if (values.length < 2) return <svg width={width} height={height} role="img" aria-label={label} />;
  const x = scaleLinear().domain([0, values.length - 1]).range([2, width - 3]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const y = scaleLinear()
    .domain(min === max ? [min - 1, max + 1] : [min, max])
    .range([height - 3, 3]);
  const stroke = line<number>().x((_, i) => x(i)).y((v) => y(v)).curve(curveMonotoneX)(values) ?? "";
  const fill =
    area<number>().x((_, i) => x(i)).y0(height).y1((v) => y(v)).curve(curveMonotoneX)(values) ?? "";
  const last = values[values.length - 1]!;
  return (
    <svg width={width} height={height} role="img" aria-label={label}>
      <path d={fill} fill={color} opacity={0.12} />
      <path d={stroke} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={x(values.length - 1)} cy={y(last)} r={2.5} fill={color} className="gs-pulse" />
    </svg>
  );
}
