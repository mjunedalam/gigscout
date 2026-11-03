import { describe, expect, it, vi } from "vitest";

import { ApiError, createClient, errorMessage, toQuery } from "./client";
import { connectLive, LIVE_EVENT_TYPES } from "./live";

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
}

describe("toQuery", () => {
  it("skips empty values and repeats array keys", () => {
    expect(toQuery({ q: "react", kind: ["project", "inbound"], page: 2, empty: "", none: undefined })).toBe(
      "?q=react&kind=project&kind=inbound&page=2",
    );
    expect(toQuery({})).toBe("");
  });
});

describe("errorMessage", () => {
  it("reads FastAPI string and validation details", () => {
    expect(errorMessage({ detail: "Nope" }, "x")).toBe("Nope");
    expect(errorMessage({ detail: [{ loc: ["body", "email"], msg: "invalid" }] }, "x")).toBe("email: invalid");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });
});

describe("askStream", () => {
  it("parses newline-delimited events even when a line is split across chunks", async () => {
    const body = [
      '{"type":"status","text":"Searching lead memory"}\n{"type":"sour',
      'ces","sources":[],"elapsed":0.1}\n{"type":"token","text":"Hel"}\n',
      '{"type":"token","text":"lo"}\n{"type":"done","elapsed":1.2}\n',
    ];
    const stream = new ReadableStream({ start(c) { body.forEach((b) => c.enqueue(new TextEncoder().encode(b))); c.close(); } });
    const fetchImpl = vi.fn(async () => new Response(stream, { status: 200 }));
    const events: string[] = [];

    await createClient("", fetchImpl).leads.askStream("hi?", (e) => events.push(e.type === "token" ? e.text : e.type));

    expect(events).toEqual(["status", "sources", "Hel", "lo", "done"]);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/leads/ask/stream");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
  });

  it("raises API errors before streaming starts", async () => {
    const api = createClient("", fakeFetch(401, { detail: "Not signed in" }));
    await expect(api.leads.askStream("hi?", () => {})).rejects.toThrow("Not signed in");
  });
});

describe("createClient", () => {
  it("sends JSON with cookies and returns the parsed body", async () => {
    const fetchImpl = fakeFetch(200, { user: { id: 1 } });
    const api = createClient("http://api", fetchImpl);

    await expect(api.auth.login("a@b.com", "pw")).resolves.toEqual({ user: { id: 1 } });

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/api/auth/login");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@b.com", password: "pw" });
  });

  it("encodes lead ids and query filters", async () => {
    const fetchImpl = fakeFetch(200, {});
    const api = createClient("", fetchImpl);
    await api.leads.get("freelancer:42");
    await api.leads.list({ kind: ["hiring"], sort: "recent" });
    expect(fetchImpl.mock.calls.map((c) => (c as unknown[])[0])).toEqual([
      "/api/leads/freelancer%3A42",
      "/api/leads?kind=hiring&sort=recent",
    ]);
  });

  it("throws ApiError with the server's message", async () => {
    const api = createClient("", fakeFetch(409, { detail: "Keep at least one active admin" }));
    await expect(api.admin.updateUser(1, { role: "member" })).rejects.toEqual(
      new ApiError(409, "Keep at least one active admin"),
    );
  });

  it("returns undefined for 204 responses", async () => {
    const api = createClient("", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api.auth.logout()).resolves.toBeUndefined();
  });
});

describe("connectLive", () => {
  class FakeEventSource {
    static CLOSED = 2;
    static last: FakeEventSource;
    readyState = 0;
    listeners = new Map<string, (m: MessageEvent<string>) => void>();
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    closed = false;

    constructor(
      public url: string,
      public init: EventSourceInit,
    ) {
      FakeEventSource.last = this;
    }

    addEventListener(type: string, fn: (m: MessageEvent<string>) => void) {
      this.listeners.set(type, fn);
    }

    close() {
      this.closed = true;
    }
  }

  it("listens to every event type, parses payloads and reports state", () => {
    const events: unknown[] = [];
    const states: string[] = [];
    const conn = connectLive("/s", (e) => events.push(e), (s) => states.push(s), FakeEventSource as never);
    const source = FakeEventSource.last;

    expect([...source.listeners.keys()]).toEqual([...LIVE_EVENT_TYPES]);
    expect(source.init.withCredentials).toBe(true);
    source.onopen?.();
    source.listeners.get("run.step")?.({ data: '{"id":1,"type":"run.step","at":"t","data":{}}' } as MessageEvent);
    conn.close();

    expect(events).toEqual([{ id: 1, type: "run.step", at: "t", data: {} }]);
    expect(states).toEqual(["connecting", "open", "closed"]);
    expect(source.closed).toBe(true);
  });
});
