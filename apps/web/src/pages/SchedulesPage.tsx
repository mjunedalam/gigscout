import type { Schedule } from "@gigscout/api-client";
import { ActionIcon, Alert, Badge, Box, Button, Group, SimpleGrid, Skeleton, Stack, Switch, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconCalendarPlus, IconCalendarTime, IconPencil, IconPlayerPlay, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { EmptyState, PageHeader } from "../components/layout-bits";
import { ScheduleEditor } from "../components/schedules/ScheduleEditor";
import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, describeCron, timeAgo } from "../lib/format";

export default function SchedulesPage() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const schedules = useQuery({ queryKey: ["schedules"], queryFn: api.schedules.list, refetchInterval: 60_000 });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles.list });
  const [editing, setEditing] = useState<Schedule | "new" | null>(null);
  const profileName = (id: number) => profiles.data?.find((p) => p.id === id)?.name ?? `Profile #${id}`;
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["schedules"] });
  const fail = (error: unknown) => notifications.show({ color: "red", message: messageOf(error) });

  const toggle = useMutation({
    mutationFn: (s: Schedule) =>
      api.schedules.update(s.id, { name: s.name, profile_id: s.profile_id, cron: s.cron, mode: s.mode, enabled: !s.enabled }),
    onSuccess: refresh,
    onError: fail,
  });
  const trigger = useMutation({
    mutationFn: (s: Schedule) => api.schedules.trigger(s.id),
    onSuccess: () => {
      refresh();
      notifications.show({ color: "signal", title: "Run started", message: "Follow it on the Runs page." });
    },
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (s: Schedule) => api.schedules.remove(s.id), onSuccess: refresh, onError: fail });

  const confirmDelete = (s: Schedule) =>
    modals.openConfirmModal({
      title: `Delete “${s.name}”?`,
      children: <Text size="sm">Future runs stop. Past runs and their leads stay.</Text>,
      labels: { confirm: "Delete schedule", cancel: "Keep it" },
      confirmProps: { color: "red" },
      onConfirm: () => remove.mutate(s),
    });

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Schedules"
        description="Let the agents scout on autopilot. Overlapping runs for the same profile are skipped automatically."
        actions={isAdmin && <Button leftSection={<IconCalendarPlus size={18} />} onClick={() => setEditing("new")}>New schedule</Button>}
      />
      {!isAdmin && <Alert variant="light" mb="md">Only admins can create or change schedules. You can still trigger them.</Alert>}
      {schedules.isError && <Alert color="red">{messageOf(schedules.error)}</Alert>}
      {schedules.isPending && <Skeleton h={240} radius="lg" />}
      {schedules.data?.length === 0 && (
        <Box className="gs-panel">
          <EmptyState icon={<IconCalendarTime size={26} />} title="Nothing scheduled">
            Create a schedule such as “weekday mornings at 9” and fresh leads will be waiting for your team.
          </EmptyState>
        </Box>
      )}
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" className="gs-stagger">
        {schedules.data?.map((s) => (
          <Box key={s.id} className="gs-panel gs-lift" p="lg" style={{ opacity: s.enabled ? 1 : 0.65 }}>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4}>
                <Text className="gs-display" fw={600} fz="lg">{s.name}</Text>
                <Text size="sm" c="var(--gs-text-muted)">{profileName(s.profile_id)} · {s.mode}</Text>
              </Stack>
              <Switch checked={s.enabled} onChange={() => toggle.mutate(s)} disabled={!isAdmin} aria-label="Enabled" />
            </Group>
            <Box my="md" p="sm" style={{ background: "var(--gs-surface-2)", borderRadius: 10 }}>
              <Text size="sm" fw={500}>{describeCron(s.cron)}</Text>
              <Text size="xs" className="gs-mono" c="var(--gs-text-muted)">{s.cron}</Text>
            </Box>
            <Stack gap={4}>
              <Group justify="space-between">
                <span className="gs-eyebrow">Next run</span>
                <Text size="sm" className="gs-mono">{s.enabled ? dateTime(s.next_run_at) : "paused"}</Text>
              </Group>
              <Group justify="space-between">
                <span className="gs-eyebrow">Last run</span>
                {s.last_run_id ? (
                  <Text size="sm" component={Link} to={`/runs/${s.last_run_id}`} c="var(--gs-signal)">{timeAgo(s.last_run_at)}</Text>
                ) : (
                  <Text size="sm" c="var(--gs-text-muted)">never</Text>
                )}
              </Group>
            </Stack>
            <Group justify="space-between" mt="md">
              <Badge variant="default" size="sm">by {s.created_by}</Badge>
              <Group gap={4}>
                <Tooltip label="Run now">
                  <ActionIcon onClick={() => trigger.mutate(s)} loading={trigger.isPending && trigger.variables?.id === s.id} aria-label="Run now">
                    <IconPlayerPlay size={18} />
                  </ActionIcon>
                </Tooltip>
                {isAdmin && (
                  <>
                    <Tooltip label="Edit">
                      <ActionIcon onClick={() => setEditing(s)} aria-label="Edit"><IconPencil size={18} /></ActionIcon>
                    </Tooltip>
                    <Tooltip label="Delete">
                      <ActionIcon color="red" onClick={() => confirmDelete(s)} aria-label="Delete"><IconTrash size={18} /></ActionIcon>
                    </Tooltip>
                  </>
                )}
              </Group>
            </Group>
          </Box>
        ))}
      </SimpleGrid>
      <ScheduleEditor
        schedule={editing === "new" ? null : editing}
        opened={editing !== null}
        onClose={() => setEditing(null)}
        profiles={profiles.data ?? []}
        onSaved={refresh}
      />
    </>
  );
}
