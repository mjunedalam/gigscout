import { Alert, Badge, Box, Button, Group, Skeleton, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBolt, IconCalendarTime, IconHandClick, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { RunStatusBadge } from "../components/badges";
import { EmptyState, PageHeader, Panel } from "../components/layout-bits";
import { RunConsole } from "../components/RunConsole";
import { StartRunButton } from "../components/StartRunButton";
import { api, messageOf } from "../lib/api";
import { duration, timeAgo } from "../lib/format";
import { useRunLines } from "../lib/live";

export default function RunsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["runs", "list"], queryFn: () => api.runs.list(100) });
  const live = runs.data?.find((r) => r.status === "running");
  const lines = useRunLines(live?.id);

  const cancel = useMutation({
    mutationFn: api.runs.cancel,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["runs"] }),
    onError: (error) => notifications.show({ color: "red", message: messageOf(error) }),
  });

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Agent runs"
        description="Start the agents on demand and watch them prospect, qualify and write in real time."
        actions={<StartRunButton />}
      />
      {live && (
        <Box mb="md">
          <Panel hero eyebrow="Live now" title={`Scouting for ${live.profile_name}`} actions={<RunStatusBadge status="running" />}>
            <RunConsole lines={lines} height={240} />
            <Button variant="subtle" size="xs" mt="sm" onClick={() => navigate(`/runs/${live.id}`)}>
              Open run →
            </Button>
          </Panel>
        </Box>
      )}
      {runs.isError && <Alert color="red">{messageOf(runs.error)}</Alert>}
      {runs.isPending && <Skeleton h={360} radius="lg" />}
      {runs.data && runs.data.length === 0 && (
        <Box className="gs-panel">
          <EmptyState icon={<IconBolt size={26} />} title="No runs yet">
            Press “Run agents now” to send the agents out for the first time.
          </EmptyState>
        </Box>
      )}
      {runs.data && runs.data.length > 0 && (
        <Box className="gs-panel" style={{ overflowX: "auto" }}>
          <Table miw={860}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Status</Table.Th>
                <Table.Th>Profile</Table.Th>
                <Table.Th>Trigger</Table.Th>
                <Table.Th>Mode</Table.Th>
                <Table.Th>New / fetched</Table.Th>
                <Table.Th>Qualified</Table.Th>
                <Table.Th>Duration</Table.Th>
                <Table.Th>When</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {runs.data.map((run) => (
                <Table.Tr key={run.id} className="gs-row-click" onClick={() => navigate(`/runs/${run.id}`)}>
                  <Table.Td><RunStatusBadge status={run.status} /></Table.Td>
                  <Table.Td><Text size="sm" fw={600}>{run.profile_name}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      {run.trigger === "schedule" ? <IconCalendarTime size={15} /> : <IconHandClick size={15} />}
                      <Text size="xs" c="var(--gs-text-muted)" lineClamp={1}>{run.triggered_by}</Text>
                    </Group>
                  </Table.Td>
                  <Table.Td><Badge variant="default">{run.mode ?? run.mode_requested}</Badge></Table.Td>
                  <Table.Td className="gs-num">{run.new_count} / {run.fetched_count}</Table.Td>
                  <Table.Td className="gs-num">{run.match_count}{run.top_score ? ` · top ${run.top_score.toFixed(2)}` : ""}</Table.Td>
                  <Table.Td className="gs-num">{duration(run.duration_seconds)}</Table.Td>
                  <Table.Td><Text size="xs" className="gs-mono" c="var(--gs-text-muted)">{timeAgo(run.created_at)}</Text></Table.Td>
                  <Table.Td>
                    {run.status === "queued" && (
                      <Button size="compact-xs" variant="subtle" color="red" leftSection={<IconX size={12} />}
                        onClick={(e) => { e.stopPropagation(); cancel.mutate(run.id); }}>
                        Cancel
                      </Button>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Box>
      )}
    </>
  );
}
