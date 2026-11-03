import type { Run, RunActivity } from "@gigscout/api-client";
import { applyActivity, type CockpitModel, emptyCockpit, finishCockpit } from "@gigscout/viz";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../lib/api";
import { useLive } from "../../lib/live";

const REPLAY_SECONDS = 18; // a finished run replays in about this long, however long it really took
const REPLAY_TICK_MS = 80;
const ACTIVE = new Set(["queued", "running"]);

export type CockpitMode = "idle" | "loading" | "live" | "replay" | "error";

export interface Cockpit {
  run: Run | null;
  mode: CockpitMode;
  model: CockpitModel;
  error: string | null;
  replay: () => void;
}

/**
 * The run the cockpit shows: the one in progress (live), otherwise the most recent finished run, replayed at a
 * watchable pace from its stored activity.
 */
export function useCockpit(): Cockpit {
  const runs = useQuery({ queryKey: ["runs", "cockpit"], queryFn: () => api.runs.list(10) });
  const { subscribeActivity } = useLive();
  const [model, setModel] = useState(emptyCockpit);
  const [mode, setMode] = useState<CockpitMode>("idle");
  const [error, setError] = useState<string | null>(null);
  const [replayToken, setReplayToken] = useState(0);
  const shownId = useRef<string | null>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const run = pickRun(runs.data ?? [], shownId.current);
  const runId = run?.id ?? null;
  const active = run ? ACTIVE.has(run.status) : false;

  // live: fold what happened so far, then apply streamed events (buffered while the backlog loads)
  useEffect(() => {
    if (!runId || !active) return;
    shownId.current = runId;
    let cancelled = false;
    const buffer: RunActivity[] = [];
    let loaded = false;
    setMode("loading");
    setModel(emptyCockpit());
    const unsubscribe = subscribeActivity((id, activity) => {
      if (id !== runId) return;
      if (loaded) setModel((m) => applyActivity(m, activity));
      else buffer.push(activity);
    });
    api.runs.activity(runId).then(
      (so_far) => {
        if (cancelled) return;
        const lastT = so_far.at(-1)?.t ?? -1;
        const fresh = buffer.filter((e) => e.t > lastT);
        loaded = true;
        setModel([...so_far, ...fresh].reduce(applyActivity, emptyCockpit()));
        setMode("live");
      },
      (e: unknown) => !cancelled && (setError(String(e)), setMode("error")),
    );
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [runId, active, subscribeActivity]);

  // the live run just finished: close it off in place rather than restarting as a replay
  useEffect(() => {
    if (run && !active && shownId.current === run.id && mode === "live") {
      setModel((m) => finishCockpit(m, m.t));
      setMode("replay");
    }
  }, [run, active, mode]);

  // replay: play the stored activity back on a compressed clock
  useEffect(() => {
    if (!runId || active) return;
    if (shownId.current === runId && modeRef.current === "live") return; // just finished live: closed off above
    shownId.current = runId;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;
    setMode("loading");
    setModel(emptyCockpit());
    api.runs.activity(runId).then(
      (events) => {
        if (cancelled) return;
        setMode("replay");
        const duration = Math.max(events.at(-1)?.t ?? 0, 0.1);
        const scale = REPLAY_SECONDS / duration;
        const started = performance.now();
        let next = 0;
        timer = setInterval(() => {
          const elapsed = ((performance.now() - started) / 1000) / scale;
          const due: RunActivity[] = [];
          while (next < events.length && events[next]!.t <= elapsed) due.push(events[next++]!);
          if (due.length) setModel((m) => due.reduce(applyActivity, m));
          if (next >= events.length) {
            clearInterval(timer);
            setModel((m) => finishCockpit(m, duration));
          }
        }, REPLAY_TICK_MS);
      },
      (e: unknown) => !cancelled && (setError(String(e)), setMode("error")),
    );
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runId, active, replayToken]);

  const replay = useCallback(() => setReplayToken((n) => n + 1), []);
  return { run, mode: run ? mode : runs.isPending ? "loading" : "idle", model, error, replay };
}

/** Prefer a run in progress; otherwise keep showing the run on screen, else the most recent finished one. */
function pickRun(runs: Run[], shownId: string | null): Run | null {
  return (
    runs.find((r) => r.status === "running") ??
    runs.find((r) => r.status === "queued") ??
    runs.find((r) => r.id === shownId) ??
    runs.find((r) => r.status === "succeeded" || r.status === "failed") ??
    null
  );
}
