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
