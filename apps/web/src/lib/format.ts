import type { Lead } from "@gigscout/api-client";
import cronstrue from "cronstrue";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

export function timeAgo(iso: string | null | undefined): string {
  return iso ? dayjs(iso).fromNow() : "—";
}

export function dateTime(iso: string | null | undefined): string {
  return iso ? dayjs(iso).format("D MMM YYYY, HH:mm") : "—";
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

export function money(lead: Lead): string {
  const budget = lead.budget;
  if (!budget) return "—";
  const value = budget.maximum ?? budget.minimum;
  if (value === null) return "—";
  const usd = budget.currency && budget.currency !== "USD" ? (budget.usd_rate ? value * budget.usd_rate : null) : value;
  if (usd === null) return `${value.toLocaleString()} ${budget.currency}`;
  const text = new Intl.NumberFormat("en", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(usd);
  return budget.kind === "hourly" ? `${text}/h` : text;
}

export function clientLabel(lead: Lead): string {
  const parts = [lead.client?.name, lead.client?.country].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Undisclosed client";
}

export function describeCron(expression: string): string {
  try {
    return cronstrue.toString(expression, { use24HourTimeFormat: true, verbose: false });
  } catch {
    return "Invalid schedule";
  }
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}`;
}

/** A wait in hours, said the way people say it: "45 min", "6 h", "3 d". */
export function waitLabel(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} d`;
}

/** US dollars without cents: "$12,500", or "$1.2M" when compact. */
export function usd(value: number | null | undefined, compact = false): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: compact ? 1 : 0, notation: compact ? "compact" : "standard",
  }).format(value);
}

/** The change from the period before, as a signed percent; null when there is nothing to compare with. */
export function change(now: number, before: number): number | null {
  if (before === 0) return now === 0 ? 0 : null;
  return Math.round(((now - before) / before) * 100);
}
