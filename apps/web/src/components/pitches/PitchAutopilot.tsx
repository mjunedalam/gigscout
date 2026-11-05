import type { PitchSettings } from "@gigscout/api-client";
import { Button, Group, NumberInput, SimpleGrid, Slider, Stack, Switch, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, messageOf } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Panel } from "../layout-bits";

const KEY = ["pitches", "settings"];

/** What the agents draft on their own after each run, and who has to approve before anything goes out. */
export function PitchAutopilot() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const saved = useQuery({ queryKey: KEY, queryFn: api.pitches.settings });
  const [value, setValue] = useState<PitchSettings | null>(null);
  useEffect(() => setValue(saved.data ?? null), [saved.data]);
  const set = (change: Partial<PitchSettings>) => setValue((v) => (v ? { ...v, ...change } : v));
  const save = useMutation({
    mutationFn: (settings: PitchSettings) => api.pitches.saveSettings(settings),
    onSuccess: (s) => {
      queryClient.setQueryData(KEY, s);
      void queryClient.invalidateQueries({ queryKey: ["pitches"] });
      notifications.show({ color: "signal", message: s.auto_draft ? "Autopilot on: the agents will draft pitches after each run" : "Pitch settings saved" });
    },
    onError: (e) => notifications.show({ color: "red", title: "Not saved", message: messageOf(e) }),
  });
  if (!value) return null;
  const changed = JSON.stringify(value) !== JSON.stringify(saved.data);

  return (
    <Panel eyebrow="Autopilot" title="The agents write, you approve"
      actions={isAdmin && <Button size="xs" disabled={!changed} loading={save.isPending} onClick={() => save.mutate(value)}>Save</Button>}>
      <Stack gap="md">
        <Switch disabled={!isAdmin} checked={value.auto_draft} onChange={(e) => set({ auto_draft: e.currentTarget.checked })}
          label="Draft pitches after every run"
          description="The agents write a pitch for each new, clean lead above the score below. Nothing is sent until a person approves it." />
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
          <Stack gap={4}>
            <Text size="sm" fw={500}>Only leads scoring at least {Math.round(value.min_score * 100)}</Text>
            <Slider disabled={!isAdmin || !value.auto_draft} min={0} max={1} step={0.05} value={value.min_score}
              label={(v) => Math.round(v * 100)} onChange={(v) => set({ min_score: v })} color="signal"
              marks={[{ value: 0.5, label: "50" }, { value: 0.7, label: "70" }, { value: 0.9, label: "90" }]} mb="md" />
          </Stack>
          <NumberInput disabled={!isAdmin || !value.auto_draft} label="At most, per run" min={1} max={25} value={value.max_per_run}
            onChange={(v) => set({ max_per_run: typeof v === "number" ? v : 5 })} />
          <NumberInput disabled={!isAdmin} label="Follow up after (days without a reply)" description="0 = never. One follow-up per email, also approved by a person."
            min={0} max={60} value={value.follow_up_days} onChange={(v) => set({ follow_up_days: typeof v === "number" ? v : 0 })} />
          <Switch disabled={!isAdmin || !value.auto_draft} checked={value.research_first}
            onChange={(e) => set({ research_first: e.currentTarget.checked })}
            label="Research each client first" description="The research agent reads the client's website before the pitch is written. Slower, more specific." mt="xs" />
          <Switch disabled={!isAdmin} checked={value.require_admin} onChange={(e) => set({ require_admin: e.currentTarget.checked })}
            label="Only owners and admins approve" description="Members can still edit drafts; an admin sends or rejects them." mt="xs" />
        </SimpleGrid>
        {!isAdmin && <Group><Text size="xs" c="var(--gs-text-muted)">An owner or admin changes these settings.</Text></Group>}
      </Stack>
    </Panel>
  );
}
