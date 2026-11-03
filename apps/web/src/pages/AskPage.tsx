import { ActionIcon, Textarea, Tooltip, UnstyledButton } from "@mantine/core";
import { IconArrowUp, IconPlayerStopFilled } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";

import { AskTurnView } from "../components/ask/AskTurn";
import { RadarSpinner } from "../components/ask/RadarSpinner";
import { useAskStream } from "../components/ask/useAskStream";
import { PageHeader } from "../components/layout-bits";
import { LeadDrawer } from "../components/LeadDrawer";
import "../components/ask/ask.css";

const SUGGESTIONS = [
  "Which leads involve mobile apps and what are their budgets?",
  "Any healthcare or fintech projects with few competing bids?",
  "Summarise the inbound enquiries from this week.",
];
const STICK_TO_BOTTOM_PX = 160;

/** Ask the lead memory. Answers stream token by token, terminal-agent style, with the leads they came from. */
export default function AskPage() {
  const [draft, setDraft] = useState("");
  const [openLead, setOpenLead] = useState<string | null>(null);
  const { turns, streaming, ask, stop } = useAskStream();
  const input = useRef<HTMLTextAreaElement>(null);

  const submit = (question: string) => {
    const text = question.trim();
    if (text.length < 3 || streaming) return;
    setDraft("");
    ask(text);
  };

  // follow the answer as it streams, unless the reader has scrolled up to read something else
  const last = turns.at(-1);
  useEffect(() => {
    const fromBottom = document.documentElement.scrollHeight - window.scrollY - window.innerHeight;
    if (fromBottom < STICK_TO_BOTTOM_PX) window.scrollTo({ top: document.documentElement.scrollHeight });
  }, [last?.answer, last?.phase, last?.sources]);

  useEffect(() => {
    if (!streaming) input.current?.focus();
  }, [streaming]);

  return (
    <>
      <PageHeader eyebrow="Lead memory" title="Ask your pipeline" description="Answers come only from collected leads, streamed as they are written, with the leads they used." />
      <div className="gs-ask">
        {turns.length === 0 && (
          <div className="gs-ask-suggest">
            <div className="gs-ask-footer"><RadarSpinner size={13} active={false} /> Try asking</div>
            {SUGGESTIONS.map((s) => (
              <UnstyledButton key={s} onClick={() => submit(s)}>› {s}</UnstyledButton>
            ))}
          </div>
        )}
        {turns.map((turn) => <AskTurnView key={turn.id} turn={turn} onOpenLead={setOpenLead} />)}

        <div className="gs-ask-composer">
          <div className="row">
            <span className="caret" aria-hidden>›</span>
            <Textarea
              ref={input}
              style={{ flex: 1 }}
              autosize
              minRows={1}
              maxRows={6}
              variant="unstyled"
              placeholder={streaming ? "Answering… press esc to stop" : "Ask about your leads…"}
              value={draft}
              maxLength={500}
              onChange={(e) => setDraft(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(draft);
                }
              }}
              aria-label="Question"
            />
            {streaming ? (
              <Tooltip label="Stop (esc)">
                <ActionIcon variant="light" color="red" size={34} onClick={stop} aria-label="Stop the answer">
                  <IconPlayerStopFilled size={16} />
                </ActionIcon>
              </Tooltip>
            ) : (
              <ActionIcon variant="filled" size={34} onClick={() => submit(draft)} disabled={draft.trim().length < 3} aria-label="Ask">
                <IconArrowUp size={18} />
              </ActionIcon>
            )}
          </div>
          <div className="gs-ask-keys">
            <span>enter to send</span>
            <span>shift+enter new line</span>
            <span>esc to stop</span>
          </div>
        </div>
      </div>
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}
