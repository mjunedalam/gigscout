import { type ConnectionState, connectLive, type LiveEvent, type Overview, type RunActivity } from "@gigscout/api-client";
import { pushWindow } from "@gigscout/viz";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import { useAuth } from "./auth";

const FEED_SIZE = 80;
const SPARK_SIZE = 40;
const RUN_LINES = 400;

export interface LiveState {
  connection: ConnectionState;
  feed: LiveEvent[];
  /** Rolling history of live metric snapshots, for sparklines. */
  history: { totalLeads: number[]; qualified: number[]; activeRuns: number[] };
  /** Streaming console lines per run id. */
  runLines: Record<string, { at: string; line: string }[]>;
}

/** Structured run activity is high-volume, so it goes to subscribers directly instead of through React state. */
export type ActivityListener = (runId: string, activity: RunActivity) => void;
interface LiveContextValue extends LiveState {
  subscribeActivity: (listener: ActivityListener) => () => void;
}

const LiveContext = createContext<LiveContextValue | null>(null);

/**
 * One Server-Sent Events connection for the whole app. Events update the activity feed and run consoles, and
 * invalidate the queries they affect, so every page stays current without polling.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const { user, workspace } = useAuth();
  const workspaceId = workspace?.id ?? null;
  const queryClient = useQueryClient();
  const [state, setState] = useState<LiveState>({
    connection: "closed",
    feed: [],
    history: { totalLeads: [], qualified: [], activeRuns: [] },
    runLines: {},
  });
  const seen = useRef(new Set<number>());
  const activityListeners = useRef(new Set<ActivityListener>());
  const subscribeActivity = useCallback((listener: ActivityListener) => {
    activityListeners.current.add(listener);
    return () => void activityListeners.current.delete(listener);
  }, []);

  useEffect(() => {
    if (!user || workspaceId === null) return;
    let cancelled = false;
    seen.current.clear();
    setState((s) => ({ ...s, feed: [], runLines: {} })); // the previous workspace's events
    api.events.recent(30).then(
      (recent) => {
        if (cancelled) return;
        recent.forEach((e) => seen.current.add(e.id));
        setState((s) => ({ ...s, feed: [...recent, ...s.feed].slice(0, FEED_SIZE) }));
      },
      () => undefined, // the stream below still delivers new events
    );

    const onEvent = (event: LiveEvent) => {
      if (seen.current.has(event.id)) return;
      seen.current.add(event.id);
      if (event.type === "run.activity") {
        const { id, ...activity } = event.data as unknown as { id: string } & RunActivity;
        activityListeners.current.forEach((listener) => listener(id, activity as RunActivity));
        return;
      }
      if (event.type === "metrics.snapshot") {
        const overview = event.data as unknown as Overview;
        queryClient.setQueryData(["metrics", "overview"], overview);
        setState((s) => ({
          ...s,
          history: {
            totalLeads: pushWindow(s.history.totalLeads, overview.total_leads, SPARK_SIZE),
            qualified: pushWindow(s.history.qualified, overview.qualified, SPARK_SIZE),
            activeRuns: pushWindow(s.history.activeRuns, overview.active_runs.length, SPARK_SIZE),
          },
        }));
        return;
      }
      setState((s) => reduceEvent(s, event));
      invalidateFor(event, queryClient);
      announce(event);
    };

    const connection = connectLive(api.events.streamUrl, onEvent, (connection) =>
      setState((s) => ({ ...s, connection })),
    );
    return () => {
      cancelled = true;
      connection.close();
    };
  }, [user, workspaceId, queryClient]);

  const value = useMemo(() => ({ ...state, subscribeActivity }), [state, subscribeActivity]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveContextValue {
  const context = useContext(LiveContext);
  if (!context) throw new Error("useLive must be used inside <LiveProvider>");
  return context;
}

export function useRunLines(runId: string | undefined) {
  const { runLines } = useLive();
  return useMemo(() => (runId ? (runLines[runId] ?? []) : []), [runLines, runId]);
}

function reduceEvent(state: LiveState, event: LiveEvent): LiveState {
  const next = { ...state, feed: event.type === "run.step" ? state.feed : [event, ...state.feed].slice(0, FEED_SIZE) };
  if (event.type === "run.step") {
    const { id, line } = event.data as { id: string; line: string };
    const lines = [...(state.runLines[id] ?? []), { at: event.at, line }].slice(-RUN_LINES);
    return { ...next, runLines: { ...state.runLines, [id]: lines } };
  }
  return next;
}

type QueryClientLike = ReturnType<typeof useQueryClient>;

function invalidateFor(event: LiveEvent, queryClient: QueryClientLike) {
  const keys: string[][] = [];
  if (event.type.startsWith("run.")) keys.push(["runs"], ["metrics"]);
  if (event.type === "run.finished") keys.push(["leads"], ["schedules"]);
  if (event.type.startsWith("lead.")) keys.push(["leads"], ["metrics"]);
  if (event.type.startsWith("schedule.")) keys.push(["schedules"]);
  if (event.type.startsWith("pitch.") || event.type === "run.finished") keys.push(["pitches"], ["outreach"]);
  if (event.type.startsWith("source.") || event.type === "run.finished") keys.push(["admin", "sources"]);
  keys.forEach((queryKey) => void queryClient.invalidateQueries({ queryKey }));
}

function announce(event: LiveEvent) {
  const data = event.data as Record<string, unknown>;
  if (event.type === "run.finished" && data.status === "cancelled") {
    notifications.show({ color: "gray", title: "Run stopped", message: String(data.profile_name) });
  } else if (event.type === "run.finished") {
    const ok = data.status === "succeeded";
    notifications.show({
      color: ok ? "signal" : "red",
      title: ok ? "Run finished" : "Run failed",
      message: ok
        ? `${String(data.profile_name)}: ${String(data.new_count)} new leads, ${String(data.match_count)} qualified`
        : String(data.profile_name),
    });
  }
  if (event.type === "source.blocked") {
    notifications.show({
      color: "orange", autoClose: 12000, title: "Website blocked",
      message: `${String(data.name)} no longer allows automated access (robots.txt), so the agents skip it.`,
    });
  }
  if (event.type === "pitch.drafted") {
    const count = Number(data.count);
    notifications.show({
      color: "violet", title: `${count} pitch${count === 1 ? "" : "es"} waiting for approval`,
      message: data.follow_up ? "Follow-ups for emails that got no reply. Open Pitches to review." : "The agents drafted them. Open Pitches to review.",
    });
  }
  if (event.type === "lead.inbound") {
    notifications.show({ color: "pink", title: "New inbound enquiry", message: String(data.title) });
  }
}
