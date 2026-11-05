import type { PitchItem, PitchQueue } from "@gigscout/api-client";
import { Anchor, Badge, Box, Grid, Group, Skeleton, Stack, Tabs, Text } from "@mantine/core";
import { IconCheck, IconInbox, IconMessageCircle, IconX } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { ScoreRing } from "../components/badges";
import { EmptyState, PageHeader, Panel } from "../components/layout-bits";
import { PitchAutopilot } from "../components/pitches/PitchAutopilot";
import { AGENT_AUTHOR, PitchEditor } from "../components/pitches/PitchEditor";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";

const QUEUES: { value: PitchQueue; label: string; icon: ReactNode }[] = [
  { value: "pending", label: "Waiting for approval", icon: <IconInbox size={15} /> },
  { value: "sent", label: "Approved", icon: <IconCheck size={15} /> },
  { value: "rejected", label: "Rejected", icon: <IconX size={15} /> },
];

/** Human in the loop: every pitch the agents (or the team) drafted waits here until a person approves or rejects it. */
export default function PitchesPage() {
  const [params, setParams] = useSearchParams();
  const queue = (QUEUES.some((q) => q.value === params.get("tab")) ? params.get("tab") : "pending") as PitchQueue;
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: ["pitches", "summary"], queryFn: api.pitches.summary });
  const list = useQuery({ queryKey: ["pitches", "list", queue], queryFn: () => api.pitches.list(queue) });
  const config = useQuery({ queryKey: ["outreach", "config"], queryFn: api.outreach.config, staleTime: 60_000 });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["pitches"] });
    void queryClient.invalidateQueries({ queryKey: ["outreach"] });
    void queryClient.invalidateQueries({ queryKey: ["leads"] }); // approving moves a new lead to "contacted"
  };
  const waiting = summary.data?.pending ?? 0;

  return (
    <>
      <PageHeader eyebrow="Outreach" title="Pitches"
        description="The agents draft pitches for your best new leads. Nothing goes out until someone here reads it, edits it if needed, and approves it."
        actions={summary.data && (
          <Badge size="lg" variant="light" color={summary.data.auto_draft ? "signal" : "gray"}>
            Autopilot {summary.data.auto_draft ? "on" : "off"}
          </Badge>
        )} />
      <Stack gap="lg">
        <Tabs value={queue} onChange={(v) => setParams(v && v !== "pending" ? { tab: v } : {}, { replace: true })} color="signal">
          <Tabs.List>
            {QUEUES.map((q) => (
              <Tabs.Tab key={q.value} value={q.value} leftSection={q.icon}
                rightSection={q.value === "pending" && waiting > 0 ? <Badge size="xs" circle color="signal">{waiting}</Badge> : undefined}>
                {q.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>

        {list.isPending && <Skeleton h={220} radius="md" />}
        {list.data?.items.length === 0 && (
          <EmptyState icon={<IconMessageCircle size={22} />} title={queue === "pending" ? "Nothing waiting for approval" : "Nothing here yet"}>
            {queue === "pending" && (summary.data?.auto_draft
              ? "The agents draft pitches at the end of each run. Start a run, or open a lead and draft one yourself."
              : "Turn on the autopilot below and the agents will draft pitches after every run.")}
          </EmptyState>
        )}
        {list.data?.items.map((item) => (
          <PitchCard key={item.outreach.id} item={item} emailReady={config.data?.email_ready ?? false} onDone={refresh} />
        ))}

        <PitchAutopilot />
      </Stack>
    </>
  );
}

function PitchCard({ item, emailReady, onDone }: { item: PitchItem; emailReady: boolean; onDone: () => void }) {
  const { outreach: o, lead } = item;
  return (
    <Panel padding={16}>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Stack gap={8}>
            <Group gap="sm" wrap="nowrap" align="flex-start">
              {item.score !== null && <ScoreRing score={item.score} size={46} />}
              <Box style={{ minWidth: 0 }}>
                <Anchor component={Link} to={`/leads?lead=${encodeURIComponent(lead.id)}`} fw={600} lineClamp={2}>{lead.title}</Anchor>
                <Text size="xs" c="var(--gs-text-muted)">{[lead.client_name, lead.source, lead.kind].filter(Boolean).join(" · ")}</Text>
              </Box>
            </Group>
            {item.reasons && <Text size="xs" c="var(--gs-text-muted)" lineClamp={4}>{item.reasons}</Text>}
            <Text size="xs" c="var(--gs-text-dim)">
              Drafted {timeAgo(o.created_at)} by {o.created_by === AGENT_AUTHOR ? "the agents" : o.created_by}
            </Text>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          {o.status === "draft" ? (
            <PitchEditor key={o.id} draft={o} emailReady={emailReady} canApprove={item.can_approve}
              leadUrl={lead.url || undefined} onDone={onDone} />
          ) : (
            <Stack gap={6}>
              <Group gap="xs">
                <Badge variant="light" color={o.status === "rejected" ? "red" : o.status === "replied" ? "signal" : "blue"}>
                  {o.status === "no_reply" ? "no reply" : o.status}
                </Badge>
                <Text size="xs" c="var(--gs-text-muted)">
                  {o.status === "rejected" ? "Rejected" : o.channel === "email" ? `Emailed ${o.to}` : "Bid posted"} by {o.reviewed_by ?? "someone"} · {timeAgo(o.reviewed_at ?? o.sent_at)}
                </Text>
              </Group>
              {o.review_note && <Text size="sm" fs="italic">“{o.review_note}”</Text>}
              {o.subject && <Text size="sm" fw={600}>{o.subject}</Text>}
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }} lineClamp={8}>{o.body}</Text>
            </Stack>
          )}
        </Grid.Col>
      </Grid>
    </Panel>
  );
}
