import type { LeadBrief } from "@gigscout/api-client";
import { Anchor, Badge, Button, Group, List, Paper, Skeleton, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconRefresh, IconSearch, IconSparkles, IconWorldWww } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, messageOf } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { timeAgo } from "../../lib/format";

/** The research agent's brief on a lead's client: who they are, what they need, and angles for the pitch. */
export function ClientBrief({ leadId }: { leadId: string }) {
  const { canWrite } = useAuth();
  const queryClient = useQueryClient();
  const key = ["research", leadId];
  const saved = useQuery({ queryKey: key, queryFn: () => api.research.get(leadId) });
  const run = useMutation({
    mutationFn: () => api.research.run(leadId),
    onSuccess: (r) => queryClient.setQueryData(key, r),
    onError: (e) => notifications.show({ color: "red", title: "Research failed", message: messageOf(e) }),
  });
  const brief = saved.data?.brief;

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <span className="gs-eyebrow">Client research</span>
        {canWrite && (
          <Button size="compact-xs" variant={brief ? "subtle" : "light"} loading={run.isPending}
            leftSection={brief ? <IconRefresh size={12} /> : <IconSearch size={12} />} onClick={() => run.mutate()}>
            {brief ? "Research again" : "Research this client"}
          </Button>
        )}
      </Group>
      {saved.isPending || run.isPending ? <Skeleton h={90} radius="md" /> : brief ? <BriefCard brief={brief} /> : (
        <Text size="xs" c="var(--gs-text-muted)">
          The research agent reads the client's own website and what GigScout already knows about them, then writes
          a brief. Pitches drafted after that use it.
        </Text>
      )}
    </Stack>
  );
}

function BriefCard({ brief: b }: { brief: LeadBrief }) {
  const sections: [string, string[]][] = [
    ["Angles for the pitch", b.brief.talking_points], ["What they likely need", b.brief.needs],
    ["Signals", b.brief.signals], ["Check before pitching", b.brief.risks],
  ];
  return (
    <Paper withBorder radius="md" p="sm">
      <Stack gap={8}>
        <Group gap={6} wrap="wrap">
          {b.made_by === "ai" && <Badge size="xs" variant="light" color="signal" leftSection={<IconSparkles size={9} />}>AI brief</Badge>}
          {b.website && (
            <Anchor href={b.website} target="_blank" rel="noopener noreferrer nofollow" size="xs">
              <IconWorldWww size={12} style={{ verticalAlign: -2 }} /> {b.website.replace(/^https?:\/\//, "")}
            </Anchor>
          )}
          {b.tech.slice(0, 6).map((t) => <Badge key={t} size="xs" variant="outline" color="gray">{t}</Badge>)}
        </Group>
        <Text size="sm">{b.brief.summary}</Text>
        {sections.filter(([, items]) => items.length > 0).map(([title, items]) => (
          <div key={title}>
            <Text size="xs" fw={600} c="var(--gs-text-muted)">{title}</Text>
            <List size="xs" spacing={2}>{items.map((i) => <List.Item key={i}>{i}</List.Item>)}</List>
          </div>
        ))}
        {b.sources.length > 0 && (
          <Text size="xs" c="var(--gs-text-dim)">
            Read: {b.sources.slice(0, 4).map((s, i) => (
              <span key={s.url}>{i > 0 && " · "}<Anchor href={s.url} target="_blank" rel="noopener noreferrer nofollow" size="xs">{s.label.slice(0, 40)}</Anchor></span>
            ))}
          </Text>
        )}
        <Text size="xs" c="var(--gs-text-dim)">Researched {timeAgo(b.created_at)}</Text>
      </Stack>
    </Paper>
  );
}
