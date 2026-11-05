import { useSearchParams } from "react-router";

/** The periods the pipeline and the report can show, in days. */
export const RANGES = ["7", "30", "90", "365"] as const;

/** Read and keep the period in the URL, so a view can be shared and survives a reload. */
export function useDays(fallback = "30"): [number, (days: string) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("days") ?? fallback;
  const days = (RANGES as readonly string[]).includes(raw) ? raw : fallback;
  const set = (value: string) => setParams((p) => { const next = new URLSearchParams(p); next.set("days", value); return next; }, { replace: true });
  return [Number(days), set];
}
