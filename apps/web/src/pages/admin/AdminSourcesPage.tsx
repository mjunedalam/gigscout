import type { SourceHealth, SourceTestResult } from "@gigscout/api-client";
import {
  ActionIcon, Alert, Anchor, Badge, Box, Button, Code, Group, SimpleGrid, Skeleton, Stack, Switch, Text, TextInput,
  ThemeIcon, Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle, IconCloudDownload, IconMailbox, IconPlayerPlay, IconPlugConnected, IconRss, IconTrash, IconWorldWww,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { SourceLibrary } from "../../components/admin/SourceLibrary";
import { UpworkPanel } from "../../components/admin/UpworkPanel";
import { PageHeader } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";

const SOURCES_KEY = ["admin", "sources"];

/** Admins connect any website by name and URL, and plug every source in or out. */
export default function AdminSourcesPage() {
  const sources = useQuery({ queryKey: SOURCES_KEY, queryFn: api.admin.sources });
  const [results, setResults] = useState<Record<string, SourceTestResult>>({});
  const test = useMutation({
    mutationFn: api.admin.testSource,
    onSuccess: (result) => setResults((r) => ({ ...r, [result.name]: result })),
  });
  const pull = sources.data?.filter((s) => s.channel === "pull") ?? [];
  const push = sources.data?.filter((s) => s.channel === "push") ?? [];

  return (
    <>
      <PageHeader eyebrow="Admin" title="Connectors"
        description="Websites the agents search for leads. Add any site by name and URL, and plug sources in or out; changes apply from the next run." />
      <AddWebsite />
      <UpworkPanel />
      <SourceLibrary />
      {sources.isError && <Alert color="red">{messageOf(sources.error)}</Alert>}
      {sources.isPending && <Skeleton h={260} radius="lg" />}
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" className="gs-stagger" mt="lg">
        {[...pull, ...push].map((s) => (
          <SourceCard key={s.name} source={s} result={results[s.name]}
            testing={test.isPending && test.variables === s.name} onTest={() => test.mutate(s.name)} />
        ))}
      </SimpleGrid>
    </>
  );
}

function AddWebsite() {
  const queryClient = useQueryClient();
  const form = useForm({
    initialValues: { name: "", url: "" },
    validate: {
      name: (v) => (v.trim().length >= 2 ? null : "Give it a short name"),
      url: (v) => (/^https?:\/\/\S+\.\S+/.test(v.trim()) ? null : "Enter a full address, e.g. https://jobs.example.com"),
    },
  });
  const add = useMutation({
    mutationFn: ({ name, url }: { name: string; url: string }) => api.admin.addConnector(name.trim(), url.trim()),
    onSuccess: (site) => {
      form.reset();
      void queryClient.invalidateQueries({ queryKey: SOURCES_KEY });
      notifications.show({
        color: "signal", title: `Connected: ${site.label ?? site.name}`,
        message: site.kind === "feed" ? "Reading its RSS/Atom feed. The agents search it from the next run."
          : "Reading listings on the page. The agents search it from the next run.",
      });
    },
    onError: (error) => notifications.show({ color: "red", autoClose: 10000, title: "Website not added", message: messageOf(error) }),
  });

  return (
    <Box className="gs-panel" p="lg" component="form" onSubmit={form.onSubmit((values) => add.mutate(values))}>
      <Group gap="sm" mb="sm">
        <ThemeIcon radius="xl" variant="light"><IconPlugConnected size={18} /></ThemeIcon>
        <Stack gap={0}>
          <Text fw={600}>Add a website</Text>
          <Text size="xs" c="var(--gs-text-muted)">
            We check it first: it must be a public site whose robots.txt allows automated access.
          </Text>
        </Stack>
      </Group>
      <Group align="flex-start" gap="sm" wrap="wrap">
        <TextInput label="Name" placeholder="Acme job board" w={220} maxLength={60} {...form.getInputProps("name")} />
        <TextInput label="Website address" placeholder="https://jobs.example.com" style={{ flex: 1, minWidth: 240 }}
          maxLength={500} {...form.getInputProps("url")} />
        <Button type="submit" mt={25} loading={add.isPending}>{add.isPending ? "Checking site…" : "Connect"}</Button>
      </Group>
      {add.isError && <Alert mt="sm" color="red" variant="light" icon={<IconAlertTriangle size={16} />}>{messageOf(add.error)}</Alert>}
    </Box>
  );
}

function SourceCard({ source: s, result, testing, onTest }: {
  source: SourceHealth; result?: SourceTestResult; testing: boolean; onTest: () => void;
}) {
  const queryClient = useQueryClient();
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: SOURCES_KEY }),
    queryClient.invalidateQueries({ queryKey: ["admin", "library"] }), // its "added" marks
  ]);
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.admin.setSourceEnabled(s.name, enabled),
    onSuccess: refresh,
    onError: (e) => notifications.show({ color: "red", title: "Could not change the source", message: messageOf(e) }),
  });
  const remove = useMutation({
    mutationFn: () => api.admin.removeConnector(s.id!),
    onSuccess: refresh,
    onError: (e) => notifications.show({ color: "red", title: "Could not remove the website", message: messageOf(e) }),
  });
  const confirmRemove = () => modals.openConfirmModal({
    title: `Remove “${s.label ?? s.name}”?`,
    children: <Text size="sm">The agents stop searching it. Leads already found stay.</Text>,
    labels: { confirm: "Remove website", cancel: "Keep it" },
    confirmProps: { color: "red" },
    onConfirm: () => remove.mutate(),
  });

  const blocked = s.status === "blocked";
  const healthy = s.enabled && !blocked && s.recent_failures === 0;
  const color = !s.enabled ? "gray" : blocked ? "red" : healthy ? "signal" : "orange";
  const badge = !s.enabled ? (s.channel === "push" ? "not set up" : "unplugged") : blocked ? "blocked" : s.recent_failures ? `${s.recent_failures} failures` : "healthy";
  const icon = s.channel === "push" ? <IconMailbox size={18} /> : s.kind === "feed" ? <IconRss size={18} />
    : s.custom ? <IconWorldWww size={18} /> : <IconCloudDownload size={18} />;
  const subtitle = s.channel === "push" ? "pushes via webhook"
    : s.custom ? `your website · reads ${s.kind === "feed" ? "its feed" : "the page"} · ${s.lead_kind ?? "project"} leads` : "built-in source";

  return (
    <Box className="gs-panel gs-lift" p="lg" style={{ opacity: s.enabled ? 1 : 0.7 }}>
      <Group justify="space-between" wrap="nowrap">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <ThemeIcon radius="xl" variant="light" color={color}>{icon}</ThemeIcon>
          <Stack gap={0} style={{ minWidth: 0 }}>
            <Text fw={600} className="gs-mono" truncate>{s.label ?? s.name}</Text>
            <Text size="xs" c="var(--gs-text-muted)">{subtitle}</Text>
          </Stack>
        </Group>
        <Badge color={color} variant="light">{badge}</Badge>
      </Group>
      {s.url && <Anchor href={s.url} target="_blank" rel="noreferrer" size="xs" mt="xs" display="block" truncate>{s.url}</Anchor>}
      {blocked && (
        <Alert mt="md" color="red" variant="light" icon={<IconAlertTriangle size={16} />}>
          This site's robots.txt no longer allows automated access, so the agents skip it.
        </Alert>
      )}
      {s.last_error && !blocked && <Code block mt="md" style={{ whiteSpace: "pre-wrap" }}>{s.last_error}</Code>}
      {result && (
        <Alert mt="md" variant="light" color={result.ok ? "signal" : "red"} title={result.ok ? `${result.count} results in ${result.latency_ms} ms` : "Test failed"}>
          {result.ok ? result.sample.map((t) => <Text key={t} size="xs" lineClamp={1}>• {t}</Text>) : result.error}
        </Alert>
      )}
      {s.channel === "pull" && (
        <Group mt="md" justify="space-between">
          <Switch size="sm" label={s.enabled ? "Plugged in" : "Unplugged"} checked={s.enabled}
            disabled={toggle.isPending} onChange={(e) => toggle.mutate(e.currentTarget.checked)}
            aria-label={`${s.enabled ? "Unplug" : "Plug in"} ${s.label ?? s.name}`} />
          <Group gap="xs">
            <Button size="xs" variant="light" leftSection={<IconPlayerPlay size={14} />} loading={testing} onClick={onTest}>
              Test now
            </Button>
            {s.custom && (
              <Tooltip label="Remove website">
                <ActionIcon variant="subtle" color="red" onClick={confirmRemove} loading={remove.isPending} aria-label={`Remove ${s.label ?? s.name}`}>
                  <IconTrash size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>
      )}
    </Box>
  );
}
