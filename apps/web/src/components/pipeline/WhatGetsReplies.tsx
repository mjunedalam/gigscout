import { Badge, Group, Progress, Skeleton, Stack, Text } from "@mantine/core";
import { IconArrowDownRight, IconArrowUpRight } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { Panel } from "../layout-bits";

/** Which kinds of messages get answered. The agents are given the same lessons when they write. */
export function WhatGetsReplies() {
  const data = useQuery({ queryKey: ["reports", "lessons"], queryFn: api.reports.lessons, staleTime: 300_000 });
  const d = data.data;
  return (
    <Panel eyebrow="Learning · last 180 days" title="What gets replies"
      actions={d && <Badge variant="light" color="gray">{d.replied} replies to {d.sent} sent</Badge>}>
      {!d ? <Skeleton h={120} /> : d.lessons.length === 0 ? (
        <Text size="sm" c="var(--gs-text-muted)">
          {d.sent < d.needed
            ? `The agents start learning after ${d.needed} sent messages (${d.sent} so far). Log replies as they come in.`
            : "No kind of message stands out yet: replies come about equally to all of them."}
        </Text>
      ) : (
        <Stack gap="sm">
          {d.lessons.slice(0, 6).map((l) => (
            <div key={l.trait}>
              <Group justify="space-between" gap="xs" wrap="nowrap">
                <Group gap={6} wrap="nowrap">
                  {l.better ? <IconArrowUpRight size={14} color="var(--mantine-color-teal-5)" /> : <IconArrowDownRight size={14} color="var(--mantine-color-red-5)" />}
                  <Text size="sm">Messages {l.trait}</Text>
                </Group>
                <Text size="sm" className="gs-num" fw={600}>{Math.round(l.rate * 100)}%</Text>
              </Group>
              <Progress value={l.rate * 100} color={l.better ? "teal" : "red"} size="sm" mt={4}
                aria-label={`${Math.round(l.rate * 100)}% reply rate`} />
              <Text size="xs" c="var(--gs-text-muted)">{l.replied} of {l.sent} · {l.better ? `${l.lift.toFixed(1)}x` : `${(1 / l.lift).toFixed(1)}x less than`} usual</Text>
            </div>
          ))}
          <Text size="xs" c="var(--gs-text-dim)">The pitch writer is given these when it drafts, so it writes more of what works.</Text>
        </Stack>
      )}
    </Panel>
  );
}
