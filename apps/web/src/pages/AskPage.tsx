import type { AskResponse } from "@gigscout/api-client";
import { ActionIcon, Alert, Avatar, Badge, Group, Paper, Stack, Text, Textarea } from "@mantine/core";
import { IconArrowUp, IconSparkles } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import Markdown from "react-markdown";

import { KindBadge } from "../components/badges";
import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel } from "../components/layout-bits";
import { api, messageOf } from "../lib/api";

interface Turn {
  question: string;
  response?: AskResponse;
  error?: string;
}

const SUGGESTIONS = [
  "Which leads involve mobile apps and what are their budgets?",
  "Any healthcare or fintech projects with few competing bids?",
  "Summarise the inbound enquiries from this week.",
];

/** Retrieval-augmented Q&A over the lead memory, with numbered citations you can open. */
export default function AskPage() {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [openLead, setOpenLead] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: (question: string) => api.leads.ask(question),
    onMutate: (question) => setTurns((t) => [...t, { question }]),
    onSuccess: (response) => setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, response } : turn))),
    onError: (error) =>
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: messageOf(error) } : turn))),
  });

  const submit = (question: string) => {
    const text = question.trim();
    if (text.length < 3 || ask.isPending) return;
    setDraft("");
    ask.mutate(text);
  };

  return (
    <>
      <PageHeader eyebrow="Lead memory" title="Ask your pipeline" description="Answers come only from collected leads, with citations." />
      <Stack gap="md" maw={900}>
        {turns.length === 0 && (
          <Panel hero eyebrow="Try asking">
            <Group gap="xs">
              {SUGGESTIONS.map((s) => (
                <Badge key={s} size="lg" variant="default" style={{ cursor: "pointer", textTransform: "none" }} onClick={() => submit(s)}>
                  {s}
                </Badge>
              ))}
            </Group>
          </Panel>
        )}
        {turns.map((turn, i) => (
          <Stack key={i} gap="sm" className="gs-rise">
            <Group justify="flex-end">
              <Paper px="md" py="sm" className="gs-panel" maw="80%">
                <Text size="sm">{turn.question}</Text>
              </Paper>
            </Group>
            <Group align="flex-start" wrap="nowrap" gap="sm">
              <Avatar color="signal" radius="xl">
                <IconSparkles size={18} />
              </Avatar>
              <Paper p="md" className="gs-panel" style={{ flex: 1 }}>
                {turn.error && <Alert color="red">{turn.error}</Alert>}
                {!turn.response && !turn.error && <Text size="sm" className="gs-pulse">Reading your leads…</Text>}
                {turn.response && (
                  <Stack gap="sm">
                    <div className="gs-markdown">
                      <Markdown>{turn.response.answer}</Markdown>
                    </div>
                    <Stack gap={6}>
                      {turn.response.sources.map((s, n) => (
                        <Group key={s.lead.id} gap="xs" wrap="nowrap" className="gs-row-click" p={4} style={{ borderRadius: 8 }}
                          onClick={() => setOpenLead(s.lead.id)}>
                          <Badge variant="outline" color="gray" className="gs-mono">[{n + 1}]</Badge>
                          <Text size="sm" lineClamp={1} style={{ flex: 1 }}>{s.lead.title}</Text>
                          <KindBadge kind={s.lead.kind} />
                        </Group>
                      ))}
                    </Stack>
                  </Stack>
                )}
              </Paper>
            </Group>
          </Stack>
        ))}
        <Paper p="sm" className="gs-panel" style={{ position: "sticky", bottom: 16 }}>
          <Group align="flex-end" wrap="nowrap">
            <Textarea
              style={{ flex: 1 }}
              autosize
              minRows={1}
              maxRows={5}
              variant="unstyled"
              placeholder="Ask about your leads…"
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
            <ActionIcon variant="filled" size={38} onClick={() => submit(draft)} loading={ask.isPending} aria-label="Ask">
              <IconArrowUp size={18} />
            </ActionIcon>
          </Group>
        </Paper>
      </Stack>
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}
