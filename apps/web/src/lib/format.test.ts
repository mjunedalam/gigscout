import type { Lead } from "@gigscout/api-client";
import { describe, expect, it } from "vitest";

import { clientLabel, describeCron, duration, money, percent, utc } from "./format";

const lead = (overrides: Partial<Lead> = {}): Lead => ({
  id: "x:1", source: "x", title: "t", description: "", url: "", kind: "project", skills: [],
  budget: null, posted_at: null, client: null, bid_count: null, ...overrides,
});

describe("format", () => {
  it("formats budgets in USD, converting with the exchange rate", () => {
    expect(money(lead())).toBe("—");
    expect(money(lead({ budget: { minimum: 100, maximum: 200, currency: "GBP", usd_rate: 1.3, kind: "fixed" } }))).toBe("$260");
    expect(money(lead({ budget: { minimum: 30, maximum: null, currency: "USD", usd_rate: null, kind: "hourly" } }))).toBe("$30/h");
    expect(money(lead({ budget: { minimum: null, maximum: 9000, currency: "INR", usd_rate: null, kind: "fixed" } }))).toBe("9,000 INR");
  });

  it("labels clients, durations, crons and percentages", () => {
    expect(clientLabel(lead())).toBe("Undisclosed client");
    expect(clientLabel(lead({ client: { name: "Acme", country: "Canada", email: null, phone: null } }))).toBe("Acme · Canada");
    expect(duration(5.25)).toBe("5.3s");
    expect(duration(125)).toBe("2m 5s");
    expect(duration(null)).toBe("—");
    expect(describeCron("0 9 * * 1-5")).toMatch(/09:00/);
    expect(describeCron("nope")).toBe("Invalid schedule");
    expect(percent(0.756)).toBe("76");
  });
});

describe("server times", () => {
  it("reads a time without a zone as UTC, not local time", () => {
    expect(utc("2026-11-06T10:00:00").toISOString()).toBe("2026-11-06T10:00:00.000Z");
    expect(utc("2026-11-06T10:00:00+02:00").toISOString()).toBe("2026-11-06T08:00:00.000Z");
    expect(utc("2026-11-06T10:00:00Z").toISOString()).toBe("2026-11-06T10:00:00.000Z");
    expect(utc("2026-11-06").format("YYYY-MM-DD")).toBe("2026-11-06");
  });
});
