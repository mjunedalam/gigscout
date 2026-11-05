import type { ReplyItem } from "@gigscout/api-client";
import { Alert, Anchor, Badge, Blockquote, Box, Button, Grid, Group, Skeleton, Spoiler, Stack, Tabs, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconInbox, IconMail, IconMailForward, IconRobot, IconSparkles } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import { EmptyState, PageHeader, Panel } from "../components/layout-bits";
import { PitchEditor } from "../components/pitches/PitchEditor";
import { INTENT_META } from "../components/replies/intents";
import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { timeAgo } from "../lib/format";

/** Client replies, read by the agents: what each one means, and the answer drafted for a person to approve. */
export default function InboxPage() {
  const [params, setParams] = useSearchParams();
  const state = params.get("tab") === "handled" ? "handled" : "open";
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: ["replies", "summary"], queryFn: api.replies.summary });
  const list = useQuery({ queryKey: ["replies", "list", state], queryFn: () => api.replies.list(state) });
  const config = useQuery({ queryKey: ["outreach", "config"], queryFn: api.outreach.config, staleTime: 60_000 });
  const pitches = useQuery({ queryKey: ["pitches", "summary"], queryFn: api.pitches.summary });
  const refresh = () => ["replies", "pitches", "outreach", "leads", "pipeline"].forEach((k) => void queryClient.invalidateQueries({ queryKey: [k] }));
  const check = useMutation({
    mutationFn: api.replies.checkMailbox,
    onSuccess: (r) => { refresh(); notifications.show({ color: "signal", message: r.new ? `${r.new} new repl${r.new === 1 ? "y" : "ies"}` : "No new replies" }); },
    onError: (e) => notifications.show({ color: "red", title: "Mailbox not read", message: messageOf(e) }),
  });

  return (
    <>
      <PageHeader eyebrow="Work" title="Inbox"
        description="Client replies, read by the agents. Each one moves its lead along the pipeline, and the answer they drafted waits for your approval."
        actions={summary.data && (
          <Group gap="xs">
            <Badge size="lg" variant="light" color={summary.data.mailbox ? "signal" : "gray"} leftSection={<IconMail size={12} />}>
              Mailbox {summary.data.mailbox ? "connected" : "not connected"}
            </Badge>
            {summary.data.mailbox && isAdmin && (
              <Button size="xs" variant="light" leftSection={<IconMailForward size={14} />} loading={check.isPending} onClick={() => check.mutate()}>
                Check now
              </Button>
            )}
          </Group>
        )} />
      {summary.data && !summary.data.mailbox && (
        <Alert variant="light" color="gray" mb="md" icon={<IconMail size={18} />}>
          Replies to emails are read automatically once the mailbox is set (GIGSCOUT_IMAP_HOST, GIGSCOUT_IMAP_USER,
          GIGSCOUT_IMAP_PASSWORD). Until then, or for marketplace messages, open a lead and use <b>Log a reply</b> on
          a sent message.
        </Alert>
      )}
      <Stack gap="lg">
        <Tabs value={state} onChange={(v) => setParams(v === "handled" ? { tab: v } : {}, { replace: true })} color="signal">
          <Tabs.List>
            <Tabs.Tab value="open" leftSection={<IconInbox size={15} />}
              rightSection={summary.data?.open ? <Badge size="xs" circle color="signal">{summary.data.open}</Badge> : undefined}>
              Needs you
            </Tabs.Tab>
            <Tabs.Tab value="handled" leftSection={<IconCheck size={15} />}>Handled</Tabs.Tab>
          </Tabs.List>
        </Tabs>
        {list.isPending && <Skeleton h={240} radius="md" />}
        {list.data?.items.length === 0 && (
          <EmptyState icon={<IconInbox size={22} />} title={state === "open" ? "No replies waiting" : "Nothing handled yet"}>
            {state === "open" && "When a client answers, it shows up here with what they want and a drafted reply."}
          </EmptyState>
        )}
        {list.data?.items.map((item) => (
          <ReplyCard key={item.reply.id} item={item} emailReady={config.data?.email_ready ?? false}
            canApprove={pitches.data?.can_approve ?? false} onDone={refresh} />
        ))}
      </Stack>
    </>
  );
}

interface ReplyCardProps {
  item: ReplyItem;
  emailReady: boolean;
  canApprove: boolean;
  onDone: () => void;
}

function ReplyCard({ item, emailReady, canApprove, onDone }: ReplyCardProps) {
  const { canWrite } = useAuth();
  const { reply: r, lead, original, answer } = item;
  const meta = INTENT_META[r.intent];
  const done = useMutation({ mutationFn: () => api.replies.done(r.id), onSuccess: onDone,
    onError: (e) => notifications.show({ color: "red", message: messageOf(e) }) });

  return (
    <Panel padding={16}>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Stack gap={8}>
            <Group gap={6} wrap="wrap">
              <Tooltip label={meta.hint}><Badge color={meta.color} variant="light">{meta.label}</Badge></Tooltip>
              {r.read_by === "ai" && <Badge size="sm" variant="outline" color="gray" leftSection={<IconSparkles size={10} />}>read by AI</Badge>}
              <Text size="xs" c="var(--gs-text-muted)">{r.from_address ?? (r.source === "pasted" ? "logged by hand" : "")} · {timeAgo(r.received_at)}</Text>
            </Group>
            <Anchor component={Link} to={`/leads?lead=${encodeURIComponent(lead.id)}`} fw={600} lineClamp={2}>{lead.title}</Anchor>
            <Text size="sm" fw={500}>{r.summary}</Text>
            <Blockquote p="xs" color={meta.color} style={{ fontSize: 13 }}>
              <Spoiler maxHeight={110} showLabel="Show all" hideLabel="Show less">
                <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{r.body}</Text>
              </Spoiler>
            </Blockquote>
            {original && (
              <Spoiler maxHeight={0} showLabel="Our message" hideLabel="Hide our message">
                <Text size="xs" c="var(--gs-text-muted)" style={{ whiteSpace: "pre-wrap" }}>{original.body}</Text>
              </Spoiler>
            )}
            {r.handled_at && <Text size="xs" c="var(--gs-text-dim)">Handled by {r.handled_by} · {timeAgo(r.handled_at)}</Text>}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          {answer && answer.status === "draft" ? (
            <Stack gap={6}>
              <Group gap={6}><IconRobot size={14} /><Text size="xs" c="var(--gs-text-muted)">The agents drafted this answer. Edit it, then approve.</Text></Group>
              <PitchEditor key={answer.id} draft={answer} emailReady={emailReady} canApprove={canApprove} leadUrl={lead.url || undefined} onDone={onDone} />
            </Stack>
          ) : answer ? (
            <Box>
              <Badge variant="light" color={answer.status === "rejected" ? "red" : "blue"} mb={6}>answer {answer.status}</Badge>
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }} lineClamp={8}>{answer.body}</Text>
            </Box>
          ) : (
            <Text size="sm" c="var(--gs-text-muted)">{meta.hint}</Text>
          )}
          {!r.handled_at && canWrite && (
            <Group justify="flex-end" mt="sm">
              <Button size="xs" variant="subtle" leftSection={<IconCheck size={14} />} loading={done.isPending} onClick={() => done.mutate()}>
                Mark handled
              </Button>
            </Group>
          )}
        </Grid.Col>
      </Grid>
    </Panel>
  );
}
