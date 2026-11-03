import type { LiveEvent } from "./types";

/** Every event type the API publishes. EventSource only delivers named events we listen for explicitly. */
export const LIVE_EVENT_TYPES = [
  "run.queued",
  "run.started",
  "run.step",
  "run.activity",
  "run.finished",
  "run.cancelled",
  "run.stopping",
  "schedule.skipped",
  "lead.updated",
  "lead.inbound",
  "metrics.snapshot",
] as const;

export type LiveEventType = (typeof LIVE_EVENT_TYPES)[number];
export type ConnectionState = "connecting" | "open" | "closed";

export interface LiveConnection {
  close: () => void;
}

/**
 * Opens the Server-Sent Events stream. The browser reconnects on its own after drops (the server sends
 * `retry: 3000`); we surface the connection state so the UI can show a live/offline indicator.
 */
export function connectLive(
  url: string,
  onEvent: (event: LiveEvent) => void,
  onState: (state: ConnectionState) => void = () => {},
  EventSourceImpl: typeof EventSource = EventSource,
): LiveConnection {
  const source = new EventSourceImpl(url, { withCredentials: true });
  onState("connecting");
  source.onopen = () => onState("open");
  source.onerror = () => onState(source.readyState === EventSourceImpl.CLOSED ? "closed" : "connecting");
  for (const type of LIVE_EVENT_TYPES) {
    source.addEventListener(type, (message) => {
      try {
        onEvent(JSON.parse((message as MessageEvent<string>).data) as LiveEvent);
      } catch (error) {
        console.error("Malformed live event", error);
      }
    });
  }
  return {
    close: () => {
      source.close();
      onState("closed");
    },
  };
}
