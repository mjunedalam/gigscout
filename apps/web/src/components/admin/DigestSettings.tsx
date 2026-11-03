import type { DigestConfig } from "@gigscout/api-client";
import {
  Alert, Badge, Box, Button, Group, Modal, NumberInput, PasswordInput, Select, Slider, Stack, Switch, TagsInput, Text,
  ThemeIcon,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconEye, IconMail, IconSend } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";

import { api, messageOf } from "../../lib/api";
import { timeAgo } from "../../lib/format";

const KEY = ["admin", "digest"];
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: `${String(h).padStart(2, "0")}:00` }));

interface FormValues {
  enabled: boolean;
  hour: string;
  emails: string[];
  slack_webhook: string;
  min_score: number;
  max_leads: number;
}

/** The daily digest: the best new leads, with a pitch each, by email and Slack at a chosen hour. */
export function DigestSettings() {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: KEY, queryFn: api.admin.digest });
  const [preview, setPreview] = useState<{ count: number; markdown: string } | null>(null);
  const form = useForm<FormValues>({
    initialValues: { enabled: false, hour: "8", emails: [], slack_webhook: "", min_score: 0.6, max_leads: 10 },
    validate: {
      emails: (v) => (v.every((e) => /^\S+@\S+\.\S+$/.test(e)) ? null : "One of the addresses is not an email"),
      slack_webhook: (v) => (!v || v.startsWith("https://hooks.slack.com/services/") ? null : "Paste a Slack incoming-webhook URL"),
    },
  });

  useEffect(() => {
    if (!config.data) return;
    const c: DigestConfig = config.data;
    form.setValues({ enabled: c.enabled, hour: String(c.hour), emails: c.emails, slack_webhook: "", min_score: c.min_score, max_leads: c.max_leads });
    form.resetDirty();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load the saved values once they arrive
  }, [config.data]);

  const save = useMutation({
    mutationFn: (v: FormValues) => api.admin.saveDigest({
      enabled: v.enabled, hour: Number(v.hour), emails: v.emails, min_score: v.min_score, max_leads: v.max_leads,
      slack_webhook: v.slack_webhook.trim() || null, // blank keeps the saved webhook
    }),
    onSuccess: (saved) => {
      queryClient.setQueryData(KEY, saved);
      notifications.show({ color: "signal", message: saved.enabled ? `Digest on: every day at ${String(saved.hour).padStart(2, "0")}:00 ${saved.timezone}` : "Digest saved (off)" });
    },
    onError: (e) => notifications.show({ color: "red", title: "Could not save the digest", message: messageOf(e) }),
  });
  const removeSlack = useMutation({
    mutationFn: () => api.admin.saveDigest({ ...currentInput(config.data!), slack_webhook: "" }),
    onSuccess: (saved) => queryClient.setQueryData(KEY, saved),
  });
  const show = useMutation({ mutationFn: api.admin.previewDigest, onSuccess: setPreview });
  const send = useMutation({
    mutationFn: api.admin.sendDigest,
    onSuccess: (r) => {
      void queryClient.invalidateQueries({ queryKey: KEY });
      notifications.show(r.sent.length
        ? { color: "signal", title: "Digest sent", message: `${r.count} leads via ${r.sent.join(" and ")}${r.errors.length ? ` (${r.errors.join("; ")})` : ""}` }
        : { color: "red", title: "Digest not sent", message: r.errors.join("; ") });
    },
    onError: (e) => notifications.show({ color: "red", title: "Could not send", message: messageOf(e) }),
  });

  const c = config.data;
  return (
    <Box className="gs-panel" p="lg" mb="lg" component="form" onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Group justify="space-between" mb="md" wrap="wrap">
        <Group gap="sm">
          <ThemeIcon radius="xl" variant="light"><IconMail size={18} /></ThemeIcon>
          <Stack gap={0}>
            <Text fw={600}>Daily digest</Text>
            <Text size="xs" c="var(--gs-text-muted)">The best new leads, with an opening line for each, so the team never has to log in to start the day.</Text>
          </Stack>
        </Group>
        <Switch label={form.values.enabled ? "On" : "Off"} {...form.getInputProps("enabled", { type: "checkbox" })} />
      </Group>
      <Stack gap="md">
        <Group grow align="flex-start" wrap="wrap">
          <Select label={`Send at (${c?.timezone ?? "UTC"})`} data={HOURS} allowDeselect={false} {...form.getInputProps("hour")} />
          <NumberInput label="Leads per digest" min={1} max={50} {...form.getInputProps("max_leads")} />
          <Box>
            <Text size="sm" fw={500} mb={6}>Minimum score: {form.values.min_score.toFixed(2)}</Text>
            <Slider min={0} max={1} step={0.05} label={(v) => v.toFixed(2)} {...form.getInputProps("min_score")} />
          </Box>
        </Group>
        <TagsInput label="Email to" description={c && !c.email_ready ? "Set GIGSCOUT_SMTP_HOST and GIGSCOUT_SMTP_FROM in apps/api/.env to send email" : "Press Enter after each address"}
          placeholder="sales@your-company.com" {...form.getInputProps("emails")} />
        <PasswordInput label="Slack incoming webhook"
          description={c?.slack_configured ? "A webhook is saved. Paste a new one to replace it, or leave blank to keep it." : "Slack › Apps › Incoming Webhooks › Add to a channel, then paste the URL"}
          placeholder={c?.slack_configured ? "•••• saved ••••" : "https://hooks.slack.com/services/…"} {...form.getInputProps("slack_webhook")} />
        {c?.slack_configured && (
          <Group gap="xs"><Badge color="signal">Slack connected</Badge>
            <Button size="compact-xs" variant="subtle" color="red" onClick={() => removeSlack.mutate()} loading={removeSlack.isPending}>Disconnect</Button>
          </Group>
        )}
        {c?.last_result && (
          <Alert variant="light" color={c.last_sent_at ? "signal" : "gray"} py="xs">
            Last digest: {c.last_result}{c.last_sent_at ? ` · ${timeAgo(c.last_sent_at)}` : ""}
          </Alert>
        )}
        <Group justify="flex-end" gap="xs">
          <Button variant="light" leftSection={<IconEye size={16} />} loading={show.isPending} onClick={() => show.mutate()}>Preview</Button>
          <Button variant="light" leftSection={<IconSend size={16} />} loading={send.isPending} onClick={() => send.mutate()}>Send now</Button>
          <Button type="submit" loading={save.isPending}>Save digest</Button>
        </Group>
      </Stack>
      <Modal opened={preview !== null} onClose={() => setPreview(null)} size="lg" title={<span className="gs-eyebrow">Digest preview · {preview?.count ?? 0} leads</span>}>
        <div className="gs-markdown"><Markdown>{preview?.markdown ?? ""}</Markdown></div>
      </Modal>
    </Box>
  );
}

function currentInput(c: DigestConfig) {
  return { enabled: c.enabled, hour: c.hour, emails: c.emails, min_score: c.min_score, max_leads: c.max_leads, slack_webhook: null };
}
