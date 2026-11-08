import type { LeadView } from "@gigscout/api-client";
import { Box, Group, Stack, Table, Text } from "@mantine/core";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";

import { clientLabel, money, timeAgo } from "../../lib/format";
import { KindBadge, ScoreRing, StatusBadge } from "../badges";
import { EmptyState } from "../layout-bits";
import { QualityBadges } from "./QualityBadges";

interface LeadTableProps {
  items: LeadView[];
  searching: boolean;
  onOpen: (id: string) => void;
}

export function LeadTable({ items, searching, onOpen }: LeadTableProps) {
  if (!items.length) {
    return (
      <Box className="gs-panel">
        <EmptyState icon={<IconInbox size={26} />} title="No leads match">
          Loosen the filters, or start a run to bring in fresh leads.
        </EmptyState>
      </Box>
    );
  }
  return (
    <Box className="gs-panel" style={{ overflowX: "auto" }}>
      <Table miw={900} stickyHeader>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={64}>Score</Table.Th>
            <Table.Th>Lead</Table.Th>
            <Table.Th w={160}>Kind</Table.Th>
            <Table.Th w={110}>Budget</Table.Th>
            <Table.Th w={80}>Bids</Table.Th>
            <Table.Th w={120}>Stage</Table.Th>
            <Table.Th w={110}>{searching ? "Match" : "Found"}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((v) => (
            <Table.Tr
              key={v.lead.id}
              className="gs-row-click"
              onClick={() => onOpen(v.lead.id)}
              onKeyDown={(e) => e.key === "Enter" && onOpen(v.lead.id)}
              tabIndex={0}
            >
              <Table.Td>
                <ScoreRing score={v.score} size={40} />
              </Table.Td>
              <Table.Td>
                <Stack gap={2}>
                  <Group gap={6} wrap="nowrap">
                    <Text fw={600} size="sm" lineClamp={1}>
                      {v.lead.title}
                    </Text>
                    {v.red_flags && <IconAlertTriangle size={14} color="var(--gs-danger)" aria-label="Has red flags" />}
                    <QualityBadges lead={v.lead} compact />
                  </Group>
                  <Text size="xs" c="var(--gs-text-muted)" lineClamp={1}>
                    {clientLabel(v.lead)} · {v.lead.source}
                    {v.assignee ? ` · 👤 ${v.assignee}` : ""}
                    {v.follow_up_on ? ` · follow up ${v.follow_up_on}` : ""}
                    {v.pitch ? ` · 💬 ${v.pitch}` : ""}
                  </Text>
                </Stack>
              </Table.Td>
              <Table.Td>
                <KindBadge kind={v.lead.kind} />
              </Table.Td>
              <Table.Td className="gs-num">{money(v.lead)}</Table.Td>
              <Table.Td className="gs-num">{v.lead.bid_count ?? "—"}</Table.Td>
              <Table.Td>
                <StatusBadge status={v.status} />
              </Table.Td>
              <Table.Td>
                <Text size="xs" className="gs-mono" c="var(--gs-text-muted)">
                  {searching && v.similarity !== null ? `${Math.round(v.similarity * 100)}%` : timeAgo(v.seen_at)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Box>
  );
}
