import type { RunMode } from "@gigscout/api-client";
import { Button, Group, Modal, Radio, Select, Stack, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconBolt } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api, messageOf } from "../lib/api";

const MODES: { value: RunMode; label: string; description: string }[] = [
  { value: "auto", label: "Auto", description: "The agent team if the local LLM is up, otherwise the fast pipeline." },
  { value: "team", label: "Agent team", description: "Head of Sales directs Prospector, Qualifier and Writer (needs Ollama)." },
  { value: "pipeline", label: "Pipeline", description: "Fixed, fast and predictable. Works without an LLM." },
];

interface StartRunButtonProps {
  size?: "xs" | "sm" | "md";
  /** Open the run's page once it starts (default). Pages that already show the live run turn this off. */
  openRun?: boolean;
}

/** Launch the agents for an agency profile, then (by default) jump to the live run. */
export function StartRunButton({ size = "md", openRun = true }: StartRunButtonProps) {
  const [opened, { open, close }] = useDisclosure();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles.list });
  const [profileId, setProfileId] = useState<string | null>(null);
  const [mode, setMode] = useState<RunMode>("auto");
  const selected = profileId ?? (profiles.data?.[0] ? String(profiles.data[0].id) : null);

  const start = useMutation({
    mutationFn: () => api.runs.start(Number(selected), mode),
    onSuccess: (run) => {
      close();
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      notifications.show({ color: "signal", title: "Agents dispatched", message: `Scouting for ${run.profile_name}` });
      if (openRun) navigate(`/runs/${run.id}`);
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not start the run", message: messageOf(error) }),
  });

  return (
    <>
      <Button size={size} leftSection={<IconBolt size={18} />} onClick={open}>
        Run agents now
      </Button>
      <Modal opened={opened} onClose={close} title={<span className="gs-eyebrow">New run</span>} size="md">
        <Stack gap="lg">
          <Select
            label="Agency profile"
            data={(profiles.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
            value={selected}
            onChange={setProfileId}
            placeholder={profiles.isPending ? "Loading…" : "Create a profile first"}
            allowDeselect={false}
          />
          <Radio.Group label="How should the agents work?" value={mode} onChange={(v) => setMode(v as RunMode)}>
            <Stack gap="xs" mt="xs">
              {MODES.map((m) => (
                <Radio.Card key={m.value} value={m.value} p="md" radius="md" className="gs-lift">
                  <Group wrap="nowrap" align="flex-start">
                    <Radio.Indicator />
                    <div>
                      <Text fw={600} size="sm">
                        {m.label}
                      </Text>
                      <Text size="xs" c="var(--gs-text-muted)">
                        {m.description}
                      </Text>
                    </div>
                  </Group>
                </Radio.Card>
              ))}
            </Stack>
          </Radio.Group>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button onClick={() => start.mutate()} loading={start.isPending} disabled={!selected} leftSection={<IconBolt size={16} />}>
              Start run
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
