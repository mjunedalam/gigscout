import type { ProfileRecord } from "@gigscout/api-client";
import { KIND_LABELS } from "@gigscout/viz";
import { ActionIcon, Alert, Badge, Box, Button, Group, SimpleGrid, Skeleton, Stack, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconBuildingStore, IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState, PageHeader } from "../components/layout-bits";
import { ProfileEditor } from "../components/profiles/ProfileEditor";
import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { timeAgo } from "../lib/format";

export default function ProfilesPage() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles.list });
  const [editing, setEditing] = useState<ProfileRecord | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (p: ProfileRecord) => api.profiles.remove(p.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profiles"] }),
    onError: (error) => notifications.show({ color: "red", message: messageOf(error) }),
  });

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Company profiles"
        description="Any kind of company: what you sell, what you are good at, and who to. The agents prospect and qualify against this."
        actions={isAdmin && <Button leftSection={<IconPlus size={18} />} onClick={() => setEditing("new")}>New profile</Button>}
      />
      {profiles.isError && <Alert color="red">{messageOf(profiles.error)}</Alert>}
      {profiles.isPending && <Skeleton h={240} radius="lg" />}
      {profiles.data?.length === 0 && (
        <Box className="gs-panel">
          <EmptyState icon={<IconBuildingStore size={26} />} title="No company profile yet">
            Describe your company so the agents know what to look for.
          </EmptyState>
        </Box>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" className="gs-stagger">
        {profiles.data?.map((p) => (
          <Box key={p.id} className="gs-panel gs-lift" p="lg">
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4}>
                <Group gap="xs">
                  <Text className="gs-display" fw={600} fz="xl">{p.name}</Text>
                  <Badge variant="outline" color="gray" style={{ textTransform: "none" }}>{p.data.company_type ?? "Software agency"}</Badge>
                </Group>
                <Text size="sm" c="var(--gs-text-muted)" lineClamp={3}>{p.data.pitch || "No pitch yet."}</Text>
              </Stack>
              {isAdmin && (
                <Group gap={4} wrap="nowrap">
                  <Tooltip label="Edit"><ActionIcon onClick={() => setEditing(p)} aria-label="Edit"><IconPencil size={18} /></ActionIcon></Tooltip>
                  <Tooltip label="Delete">
                    <ActionIcon color="red" aria-label="Delete" onClick={() => modals.openConfirmModal({
                      title: `Delete “${p.name}”?`,
                      children: <Text size="sm">Its schedules are deleted too. Leads already found stay.</Text>,
                      labels: { confirm: "Delete", cancel: "Cancel" },
                      confirmProps: { color: "red" },
                      onConfirm: () => remove.mutate(p),
                    })}><IconTrash size={18} /></ActionIcon>
                  </Tooltip>
                </Group>
              )}
            </Group>
            <Stack gap="sm" mt="md">
              <TagRow label="Services" values={p.data.services} />
              <TagRow label="Capabilities" values={p.data.skills} accent />
              <TagRow label="Searches" values={p.data.keywords} />
              <TagRow label="Looks on" values={p.data.sources ?? ["every connected source"]} />
              <TagRow label="Industries" values={p.data.industries} />
              <TagRow label="Lead kinds" values={p.data.kinds.map((k) => KIND_LABELS[k])} />
              <Group gap="xl">
                <Fact label="Min deal" value={p.data.min_budget_usd ? `$${p.data.min_budget_usd.toLocaleString()}` : "any"} />
                <Fact label="Markets" value={p.data.target_countries.length ? `${p.data.target_countries.length} countries` : "worldwide"} />
                <Fact label="Updated" value={timeAgo(p.updated_at)} />
              </Group>
            </Stack>
          </Box>
        ))}
      </SimpleGrid>
      <ProfileEditor profile={editing === "new" ? null : editing} opened={editing !== null} onClose={() => setEditing(null)} />
    </>
  );
}

function TagRow({ label, values, accent }: { label: string; values: string[]; accent?: boolean }) {
  if (!values.length) return null;
  return (
    <Group gap={6} align="center">
      <Text className="gs-eyebrow" w={84}>{label}</Text>
      {values.slice(0, 10).map((v) => (
        <Badge key={v} variant={accent ? "light" : "default"} style={{ textTransform: "none" }}>{v}</Badge>
      ))}
      {values.length > 10 && <Text size="xs" c="var(--gs-text-muted)">+{values.length - 10}</Text>}
    </Group>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={0}>
      <span className="gs-eyebrow">{label}</span>
      <Text size="sm" className="gs-num">{value}</Text>
    </Stack>
  );
}
