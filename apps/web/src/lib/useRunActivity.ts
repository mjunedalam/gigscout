import type { RunActivity } from "@gigscout/api-client";
import { useEffect, useState } from "react";

import { api } from "./api";
import { useLive } from "./live";

export interface RunActivityState {
  events: RunActivity[];
  loading: boolean;
  error: string | null;
}

/** Everything a run's agents did, in order: the stored log, then live events while the run is going. */
export function useRunActivity(runId: string | null, active: boolean): RunActivityState {
  const { subscribeActivity } = useLive();
  const [state, setState] = useState<RunActivityState>({ events: [], loading: true, error: null });

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    let loaded = false;
    const buffer: RunActivity[] = [];
    setState({ events: [], loading: true, error: null });
    const unsubscribe = active
      ? subscribeActivity((id, event) => {
          if (id !== runId) return;
          if (loaded) setState((s) => ({ ...s, events: [...s.events, event] }));
          else buffer.push(event);
        })
      : () => undefined;
    api.runs.activity(runId).then(
      (soFar) => {
        if (cancelled) return;
        const lastT = soFar.at(-1)?.t ?? -1;
        loaded = true;
        setState({ events: [...soFar, ...buffer.filter((e) => e.t > lastT)], loading: false, error: null });
      },
      (e: unknown) => !cancelled && setState({ events: [], loading: false, error: String(e) }),
    );
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [runId, active, subscribeActivity]);

  return state;
}
