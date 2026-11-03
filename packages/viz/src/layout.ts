// Pure data → geometry helpers. Kept out of components so they are easy to unit test.
import type { LeadKind, TimeseriesRow } from "@gigscout/api-client";
import { LEAD_KINDS } from "@gigscout/api-client";
import { stack, stackOrderNone, stackOffsetNone, type Series } from "d3";

export type StackedSeries = Series<TimeseriesRow, LeadKind>[];

export function stackByKind(rows: readonly TimeseriesRow[], kinds: readonly LeadKind[] = LEAD_KINDS): StackedSeries {
  return stack<TimeseriesRow, LeadKind>()
    .keys(kinds)
    .order(stackOrderNone)
    .offset(stackOffsetNone)([...rows]);
}

export function stackMax(series: StackedSeries): number {
  let max = 0;
  for (const layer of series) for (const point of layer) max = Math.max(max, point[1]);
  return max;
}

export interface FunnelBar {
  stage: string;
  count: number;
  width: number; // 0..1 of the widest stage
  conversion: number | null; // share of the previous stage that reached this one
}

export function funnelBars(stages: readonly { stage: string; count: number }[]): FunnelBar[] {
  const max = Math.max(1, ...stages.map((s) => s.count));
  return stages.map((s, i) => {
    const previous = i > 0 ? stages[i - 1] : undefined;
    return {
      stage: s.stage,
      count: s.count,
      width: s.count / max,
      conversion: previous && previous.count > 0 && s.stage !== "lost" ? s.count / previous.count : null,
    };
  });
}

/** Rolling buffer for live sparklines: append a value, keep the last `size`. Returns a new array. */
export function pushWindow(values: readonly number[], value: number, size: number): number[] {
  const next = [...values, value];
  return next.length > size ? next.slice(next.length - size) : next;
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}
