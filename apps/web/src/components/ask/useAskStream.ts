import type { AskStreamEvent, LeadView } from "@gigscout/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, messageOf } from "../../lib/api";

export type TurnPhase = "searching" | "reading" | "writing" | "done" | "stopped" | "error";

export interface AskTurn {
  id: number;
  question: string;
  phase: TurnPhase;
  status: string;
  sources: LeadView[] | null;
  sourcesElapsed: number;
  answer: string;
  startedAt: number;
  elapsed: number | null;
  error: string | null;
}

const ACTIVE: ReadonlySet<TurnPhase> = new Set(["searching", "reading", "writing"]);
export const isActive = (turn: AskTurn) => ACTIVE.has(turn.phase);

/** One conversation with the lead memory; each question streams its answer and can be stopped (Esc). */
export function useAskStream() {
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const streaming = turns.some(isActive);

  const update = useCallback((id: number, change: (turn: AskTurn) => Partial<AskTurn>) => {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...change(t) } : t)));
  }, []);

  const ask = useCallback(
    (question: string) => {
      const id = nextId.current++;
      const startedAt = performance.now();
      const seconds = () => (performance.now() - startedAt) / 1000;
      setTurns((all) => [...all, {
        id, question, phase: "searching", status: "Searching lead memory", sources: null, sourcesElapsed: 0,
        answer: "", startedAt, elapsed: null, error: null,
      }]);
      const abort = new AbortController();
      controller.current = abort;
      const onEvent = (event: AskStreamEvent) => {
        switch (event.type) {
          case "status":
            update(id, (t) => ({ status: event.text, phase: t.sources ? "reading" : "searching" }));
            break;
          case "sources":
            update(id, () => ({ sources: event.sources, sourcesElapsed: event.elapsed, phase: "reading" }));
            break;
          case "token":
            update(id, (t) => ({ answer: t.answer + event.text, phase: "writing" }));
            break;
          case "done":
            update(id, () => ({ phase: "done", elapsed: seconds() }));
            break;
          case "error":
            update(id, () => ({ phase: "error", error: event.message, elapsed: seconds() }));
            break;
        }
      };
      api.leads.askStream(question, onEvent, { signal: abort.signal }).then(
        () => update(id, (t) => (isActive(t) ? { phase: "done", elapsed: seconds() } : {})),
        (error: unknown) => update(id, (t) =>
          abort.signal.aborted
            ? { phase: "stopped", elapsed: seconds() }
            : { phase: "error", error: t.error ?? messageOf(error), elapsed: seconds() }),
      );
    },
    [update],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  // Esc stops the answer being written, like a terminal agent
  useEffect(() => {
    if (!streaming) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && stop();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming, stop]);

  useEffect(() => () => controller.current?.abort(), []); // leaving the page stops the stream

  return { turns, streaming, ask, stop };
}
