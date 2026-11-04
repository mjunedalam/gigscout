import { ActionIcon, Alert, Anchor, Badge, Box, Button, Group, Skeleton, Table, Text, TextInput, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconExternalLink, IconRefresh, IconTrophy, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader, Panel } from "../components/layout-bits";
import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime } from "../lib/format";

const KEY = ["competitors"];

function money(amount: number | null, currency: string | null): string {
  if (!amount) return "—";
  const symbol = { GBP: "£", USD: "$", EUR: "€" }[currency ?? ""] ?? "";
  if (amount >= 1_000_000) return `${symbol}${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `${symbol}${Math.round(amount / 1_000)}k`;
  return `${symbol}${Math.round(amount)}`;
}

/** The companies this workspace competes with, and the public contracts they have been winning. */
export default function CompetitorsPage() {
  const { isAdmin, canWrite } = useAuth();
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: [...KEY, "list"], queryFn: api.competitors.list });
  const wins = useQuery({ queryKey: [...KEY, "wins"], queryFn: () => api.competitors.wins() });
  const [name, setName] = useState("");
  const refresh = () => void queryClient.invalidateQueries({ queryKey: KEY });
  const failed = (title: string) => (e: unknown) => notifications.show({ color: "red", title, message: messageOf(e) });

  const add = useMutation({ mutationFn: () => api.competitors.add(name.trim()), onSuccess: () => { setName(""); refresh(); }, onError: failed("Not added") });
  const remove = useMutation({ mutationFn: api.competitors.remove, onSuccess: refresh, onError: failed("Not removed") });
  const check = useMutation({
    mutationFn: api.competitors.check,
    onSuccess: (r) => {
      refresh();
      notifications.show({ color: r.new ? "signal" : "gray", message: r.new ? `${r.new} new win${r.new === 1 ? "" : "s"} found in ${r.notices} award notices` : `No new wins in ${r.notices} award notices` });
    },
    onError: failed("Could not check"),
  });

  return (
    <>
      <PageHeader eyebrow="Insights" title="Competitor watch"
        description="Public contracts your competitors won, from UK Find a Tender award notices (the last 30 days, checked daily). See who buys from them, and for how much."
        actions={canWrite && (list.data?.length ?? 0) > 0 && (
          <Button variant="light" leftSection={<IconRefresh size={16} />} loading={check.isPending} onClick={() => check.mutate()}>Check now</Button>
        )} />
      <Panel eyebrow="Watching" title="Your competitors">
        <Group gap="xs" mb={isAdmin ? "md" : 0}>
          {list.isPending && <Skeleton h={28} w={240} />}
          {list.data?.length === 0 && <Text size="sm" c="var(--gs-text-muted)">Nobody yet. {isAdmin ? "Add the agencies you lose deals to." : "An owner or admin can add them."}</Text>}
          {list.data?.map((c) => (
            <Badge key={c.id} size="lg" variant="light" color={c.wins ? "orange" : "gray"} tt="none"
              rightSection={isAdmin && (
                <ActionIcon size="xs" variant="transparent" color="gray" aria-label={`Stop watching ${c.name}`} onClick={() => remove.mutate(c.id)}>
                  <IconX size={12} />
                </ActionIcon>
              )}>
              {c.name} · {c.wins} win{c.wins === 1 ? "" : "s"}
            </Badge>
          ))}
        </Group>
        {isAdmin && (
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) add.mutate(); }}>
            <Group align="flex-end">
              <TextInput flex="1 1 260px" label="Add a competitor" placeholder="Their company name, e.g. Acme Digital Ltd"
                value={name} maxLength={120} onChange={(e) => setName(e.currentTarget.value)} />
              <Button type="submit" loading={add.isPending} disabled={name.trim().length < 2}>Watch</Button>
            </Group>
          </form>
        )}
      </Panel>
      <Box mt="lg">
        <Panel eyebrow="Their wins" title="Contracts they won">
          {wins.isError && <Alert color="red">{messageOf(wins.error)}</Alert>}
          {wins.data?.length === 0 && (
            <Text size="sm" c="var(--gs-text-muted)">No wins found yet. Public awards appear here as they are published.</Text>
          )}
          {!!wins.data?.length && (
            <Box style={{ overflowX: "auto" }}>
              <Table miw={760} verticalSpacing="sm">
                <Table.Thead>
                  <Table.Tr><Table.Th>Awarded</Table.Th><Table.Th>Competitor</Table.Th><Table.Th>Contract</Table.Th><Table.Th>Buyer</Table.Th><Table.Th ta="right">Value</Table.Th></Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {wins.data.map((w) => (
                    <Table.Tr key={w.id}>
                      <Table.Td><Text size="xs" className="gs-mono" c="var(--gs-text-muted)">{w.awarded_at ? dateTime(w.awarded_at) : "—"}</Text></Table.Td>
                      <Table.Td>
                        <Tooltip label={`Named in the notice as ${w.supplier}`}>
                          <Group gap={6} wrap="nowrap"><IconTrophy size={14} color="var(--mantine-color-orange-5)" /><Text size="sm" fw={600}>{w.competitor}</Text></Group>
                        </Tooltip>
                      </Table.Td>
                      <Table.Td>
                        <Anchor href={w.url} target="_blank" rel="noopener noreferrer" size="sm">
                          <Group gap={4} wrap="nowrap"><Text size="sm" lineClamp={1}>{w.title}</Text><IconExternalLink size={12} /></Group>
                        </Anchor>
                      </Table.Td>
                      <Table.Td><Text size="sm" lineClamp={1}>{w.buyer}</Text></Table.Td>
                      <Table.Td ta="right"><Text size="sm" className="gs-num">{money(w.amount, w.currency)}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Box>
          )}
        </Panel>
      </Box>
    </>
  );
}
