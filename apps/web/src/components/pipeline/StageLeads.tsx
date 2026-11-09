import type { PipelineStage } from "@gigscout/api-client";
import { STAGE_COLORS } from "@gigscout/viz";
import { Group, Table, Text, UnstyledButton } from "@mantine/core";
import { IconListDetails } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { timeAgo, usd } from "../../lib/format";
import { StatusBadge } from "../badges";
import { EmptyState, Panel } from "../layout-bits";
import { TableSkeleton } from "../skeletons";

interface StageLeadsProps {
  stage: PipelineStage;
  days: number;
  onOpen: (leadId: string) => void;
}

/** The leads behind one pipeline step: which reached it in the period, and when. */
export function StageLeads({ stage, days, onOpen }: StageLeadsProps) {
  const list = useQuery({ queryKey: ["pipeline", "leads", stage, days], queryFn: () => api.pipeline.leads(stage, days) });
  const items = list.data?.items ?? [];
  return (
    <Panel eyebrow={`${days} days · newest first`}
      title={<Group gap={8}><span className="gs-dot" style={{ background: STAGE_COLORS[stage] }} />{list.data?.label ?? stage}: the leads</Group>}>
      {list.isPending && <TableSkeleton rows={4} label="Loading stage leads" />}
      {list.data && items.length === 0 && (
        <EmptyState icon={<IconListDetails size={22} />} title="No leads reached this step in the period" />
      )}
      {items.length > 0 && (
        <Table.ScrollContainer minWidth={560}>
          <Table highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Lead</Table.Th>
                <Table.Th>Source</Table.Th>
                <Table.Th>Status now</Table.Th>
                <Table.Th ta="right">Score</Table.Th>
                {stage === "won" && <Table.Th ta="right">Value</Table.Th>}
                <Table.Th ta="right">Reached</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((lead) => (
                <Table.Tr key={lead.id}>
                  <Table.Td maw={360}>
                    <UnstyledButton onClick={() => onOpen(lead.id)}>
                      <Text size="sm" fw={500} lineClamp={1}>{lead.title}</Text>
                      {lead.client_name && <Text size="xs" c="var(--gs-text-muted)">{lead.client_name}</Text>}
                    </UnstyledButton>
                  </Table.Td>
                  <Table.Td><Text size="xs">{lead.source}</Text></Table.Td>
                  <Table.Td><StatusBadge status={lead.status} /></Table.Td>
                  <Table.Td ta="right" className="gs-num">{lead.score !== null ? Math.round(lead.score * 100) : "—"}</Table.Td>
                  {stage === "won" && <Table.Td ta="right" className="gs-num">{usd(lead.deal_value_usd)}</Table.Td>}
                  <Table.Td ta="right"><Text size="xs" c="var(--gs-text-muted)">{timeAgo(lead.at)}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Panel>
  );
}
