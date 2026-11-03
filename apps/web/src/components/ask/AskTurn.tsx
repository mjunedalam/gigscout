import { Collapse, UnstyledButton } from "@mantine/core";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";

import { KindBadge } from "../badges";
import { RadarSpinner } from "./RadarSpinner";
import { type AskTurn as Turn, isActive } from "./useAskStream";

/** What the scout is busy with, rotated while it works (our version of Claude Code's "Thinking…"). */
const VERBS = ["Scouting", "Sifting leads", "Weighing budgets", "Reading briefs", "Cross-checking bids", "Sizing up clients", "Drafting the answer"];

function useTicker(active: boolean, ms: number) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setTick((n) => n + 1), ms);
    return () => clearInterval(timer);
  }, [active, ms]);
  return tick;
}

/** Turn "[3]" citations into links the reader can open (only for leads that were actually retrieved). */
function linkCitations(answer: string, sourceCount: number): string {
  return answer.replace(/\[(\d{1,2})\](?!\()/g, (match, n: string) =>
    Number(n) >= 1 && Number(n) <= sourceCount ? `[[${n}]](#lead-${n})` : match);
}

const words = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0);
const seconds = (s: number) => (s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`);

/** "⏺ Searched lead memory  ⎿ 8 leads · 0.4s", expandable to the leads it read. */
function SearchLine({ turn, onOpenLead }: { turn: Turn; onOpenLead: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const done = turn.sources !== null;
  return (
    <div className="gs-ask-tool">
      <div className="gs-ask-tool-head">
        <span className={`gs-ask-dot${done ? " is-done" : " is-running"}`} aria-hidden>⏺</span>
        <span className="gs-ask-tool-name">{done ? "Searched lead memory" : "Searching lead memory"}</span>
      </div>
      {done && (
        <div className="gs-ask-tool-result">
          <span className="gs-ask-elbow" aria-hidden>⎿</span>
          <UnstyledButton className="gs-ask-tool-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {turn.sources!.length} {turn.sources!.length === 1 ? "lead" : "leads"} · {seconds(turn.sourcesElapsed)}
            {turn.sources!.length > 0 && <span className="gs-ask-hint">{open ? " (hide)" : " (show)"}</span>}
          </UnstyledButton>
        </div>
      )}
      <Collapse in={open}>
        <ol className="gs-ask-sources">
          {turn.sources?.map((s) => (
            <li key={s.lead.id}>
              <UnstyledButton onClick={() => onOpenLead(s.lead.id)} className="gs-ask-source">
                <span className="gs-ask-source-title">{s.lead.title}</span>
                <KindBadge kind={s.lead.kind} />
              </UnstyledButton>
            </li>
          ))}
        </ol>
      </Collapse>
    </div>
  );
}

/** The live status line: radar, shimmering verb, elapsed time and words written, and how to stop. */
function WorkingLine({ turn }: { turn: Turn }) {
  const tick = useTicker(true, 100);
  const verb = VERBS[Math.floor(tick / 30) % VERBS.length];
  const elapsed = (performance.now() - turn.startedAt) / 1000;
  const n = words(turn.answer);
  return (
    <div className="gs-ask-working" role="status" aria-live="polite">
      <RadarSpinner size={15} />
      <span className="gs-ask-shimmer">{turn.phase === "writing" ? verb : turn.status}…</span>
      <span className="gs-ask-meta">
        ({seconds(elapsed)}{n ? ` · ↓ ${n} words` : ""} · <kbd>esc</kbd> to stop)
      </span>
    </div>
  );
}

export function AskTurnView({ turn, onOpenLead }: { turn: Turn; onOpenLead: (id: string) => void }) {
  const active = isActive(turn);
  return (
    <article className="gs-ask-turn">
      <div className="gs-ask-prompt">
        <span aria-hidden>›</span>
        <p>{turn.question}</p>
      </div>
      <div className="gs-ask-reply">
        <SearchLine turn={turn} onOpenLead={onOpenLead} />
        {turn.answer && (
          <div className={`gs-ask-answer${turn.phase === "writing" ? " is-streaming" : ""}`}>
            <span className={`gs-ask-dot is-answer`} aria-hidden>⏺</span>
            <div className="gs-markdown">
              <Markdown
                components={{
                  a: ({ href, children }) => {
                    const n = href?.startsWith("#lead-") ? Number(href.slice(6)) : 0;
                    const lead = n ? turn.sources?.[n - 1] : undefined;
                    if (!lead) return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
                    return (
                      <UnstyledButton component="span" className="gs-ask-cite" title={lead.lead.title} onClick={() => onOpenLead(lead.lead.id)}>
                        {children}
                      </UnstyledButton>
                    );
                  },
                }}
              >
                {linkCitations(turn.answer, turn.sources?.length ?? 0)}
              </Markdown>
            </div>
          </div>
        )}
        {active && <WorkingLine turn={turn} />}
        {turn.phase === "done" && turn.elapsed !== null && (
          <div className="gs-ask-footer">
            <RadarSpinner size={13} active={false} /> Answered in {seconds(turn.elapsed)} · {words(turn.answer)} words
            {turn.sources?.length ? ` · ${turn.sources.length} sources` : ""}
          </div>
        )}
        {turn.phase === "stopped" && <div className="gs-ask-footer is-stopped"><span className="gs-ask-elbow">⎿</span> Stopped by you</div>}
        {turn.phase === "error" && <div className="gs-ask-footer is-error"><span className="gs-ask-elbow">⎿</span> {turn.error}</div>}
      </div>
    </article>
  );
}
