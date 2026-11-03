import type { ProfileRecord, RunMode, Schedule, ScheduleInput } from "@gigscout/api-client";
import { Alert, Button, Chip, Group, Modal, Select, Stack, Switch, Text, TextInput, Timeline } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconClock } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, messageOf } from "../../lib/api";
import { CRON_PRESETS } from "../../lib/cron";
import { dateTime, describeCron } from "../../lib/format";

interface ScheduleEditorProps {
  schedule: Schedule | null;
  opened: boolean;
  onClose: () => void;
  onSaved: () => void;
  profiles: ProfileRecord[];
}

export function ScheduleEditor({ schedule, opened, onClose, onSaved, profiles }: ScheduleEditorProps) {
  const form = useForm<ScheduleInput>({
    initialValues: { name: "", profile_id: 0, cron: "0 9 * * 1-5", mode: "auto", enabled: true },
    validate: {
      name: (v) => (v.trim() ? null : "Give it a name"),
      profile_id: (v) => (v ? null : "Pick an agency profile"),
    },
  });

  useEffect(() => {
    if (!opened) return;
    form.setValues(
      schedule
        ? { name: schedule.name, profile_id: schedule.profile_id, cron: schedule.cron, mode: schedule.mode, enabled: schedule.enabled }
        : { name: "", profile_id: profiles[0]?.id ?? 0, cron: "0 9 * * 1-5", mode: "auto", enabled: true },
    );
    form.resetDirty();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [opened, schedule]);

  const [cron] = useDebouncedValue(form.values.cron, 300);
  const preview = useQuery({ queryKey: ["cron", cron], queryFn: () => api.schedules.preview(cron), enabled: opened && cron.length >= 9 });

  const save = useMutation({
    mutationFn: (input: ScheduleInput) => (schedule ? api.schedules.update(schedule.id, input) : api.schedules.create(input)),
    onSuccess: () => {
      notifications.show({ color: "signal", message: schedule ? "Schedule updated" : "Schedule created" });
      onSaved();
      onClose();
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not save", message: messageOf(error) }),
  });

  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={<span className="gs-eyebrow">{schedule ? "Edit schedule" : "New schedule"}</span>}>
      <form onSubmit={form.onSubmit((v) => save.mutate({ ...v, name: v.name.trim(), cron: v.cron.trim() }))}>
        <Stack gap="md">
          <TextInput label="Name" placeholder="Weekday mornings" {...form.getInputProps("name")} />
          <Group grow>
            <Select
              label="Agency profile"
              data={profiles.map((p) => ({ value: String(p.id), label: p.name }))}
              value={form.values.profile_id ? String(form.values.profile_id) : null}
              onChange={(v) => form.setFieldValue("profile_id", Number(v))}
              error={form.errors.profile_id}
              allowDeselect={false}
            />
            <Select
              label="Mode"
              data={[{ value: "auto", label: "Auto" }, { value: "team", label: "Agent team" }, { value: "pipeline", label: "Pipeline" }]}
              value={form.values.mode}
              onChange={(v) => form.setFieldValue("mode", (v ?? "auto") as RunMode)}
              allowDeselect={false}
            />
          </Group>
          <Stack gap={6}>
            <Text size="sm" fw={500}>When</Text>
            <Chip.Group multiple={false} value={form.values.cron} onChange={(v) => form.setFieldValue("cron", v)}>
              <Group gap={6}>
                {CRON_PRESETS.map((p) => (
                  <Chip key={p.cron} value={p.cron} size="xs" variant="outline">{p.label}</Chip>
                ))}
              </Group>
            </Chip.Group>
            <TextInput
              leftSection={<IconClock size={16} />}
              className="gs-mono"
              description="Cron: minute hour day-of-month month day-of-week"
              {...form.getInputProps("cron")}
            />
          </Stack>
          {preview.data && !preview.data.valid && <Alert color="red" variant="light">{preview.data.error}</Alert>}
          {preview.data?.valid && (
            <Stack gap="xs" p="md" style={{ background: "var(--gs-surface-2)", borderRadius: 12 }}>
              <Text fw={600} size="sm">{describeCron(form.values.cron)}</Text>
              <Timeline bulletSize={14} lineWidth={2} active={0}>
                {preview.data.next_runs.map((t) => (
                  <Timeline.Item key={t} title={<Text size="xs" className="gs-mono">{dateTime(t)}</Text>} />
                ))}
              </Timeline>
            </Stack>
          )}
          <Switch label="Enabled" {...form.getInputProps("enabled", { type: "checkbox" })} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={preview.data?.valid === false}>
              {schedule ? "Save changes" : "Create schedule"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
