import { Donut, RUN_STATUS_COLORS, RunTimeline, STATUS_COLORS } from "@gigscout/viz";
import { Alert, Badge, Center, Grid, Group, SimpleGrid, Skeleton, Stack, Text, ThemeIcon } from "@mantine/core";
import {
  IconBrain,
  IconCalendarTime,
  IconCheck,
  IconDatabase,
  IconMailbox,
  IconPlugConnected,
  IconServer,
  IconX,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import { PageHeader, Panel, StatTile } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";
import { duration } from "../../lib/format";

export default function AdminSystemPage() {
  const navigate = useNavigate();
  const system = useQuery({ queryKey: ["admin", "system"], queryFn: api.admin.system, refetchInterval: 15_000 });
  const overview = useQuery({ queryKey: ["metrics", "overview"], queryFn: api.metrics.overview });
  const analytics = useQuery({ queryKey: ["metrics", "analytics", 30], queryFn: () => api.metrics.analytics(30) });
  const s = system.data;
  const o = overview.data;
  const runStatusSlices = Object.entries(
    (analytics.data?.runs ?? []).reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {}),
  ).map(([key, value]) => ({ key, label: key, value, color: RUN_STATUS_COLORS[key as keyof typeof RUN_STATUS_COLORS] }));

  return (
    <>
      <PageHeader eyebrow="Admin" title="System health" description="Is everything the agents depend on up and healthy?" />
      {system.isError && <Alert color="red">{messageOf(system.error)}</Alert>}
      {!s ? (
        <Skeleton h={420} radius="lg" />
      ) : (
        <>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="md" className="gs-stagger">
            <StatTile label="Uptime" value={duration(s.uptime_seconds)} hint={`v${s.version} · Python ${s.python}`} icon={<IconServer size={20} />} />
            <StatTile label="Leads stored" value={s.vector_store.leads} hint={s.embedding_model} icon={<IconDatabase size={20} />} />
            <StatTile label="Runs recorded" value={s.database.runs} hint={`${s.database.users} users`} icon={<IconCalendarTime size={20} />} />
            <StatTile label="Live dashboards" value={s.live_clients} hint="open event streams" icon={<IconPlugConnected size={20} />} />
          </SimpleGrid>
          <Grid gutter="md">
            <Grid.Col span={{ base: 12, lg: 5 }}>
              <Panel eyebrow="Dependencies" title="Service checks">
                <Stack gap="sm">
                  <Check icon={<IconBrain size={18} />} label="Local LLM (Ollama)" ok={s.llm.reachable_now}
                    detail={`${s.llm.provider} · ${s.llm.model}${s.llm.available ? "" : " · agents running on heuristics"}`} />
                  <Check icon={<IconCalendarTime size={18} />} label="Scheduler" ok={s.scheduler.running}
                    detail={`${s.scheduler.jobs} active job(s) · ${s.scheduler.timezone}`} />
                  <Check icon={<IconMailbox size={18} />} label="Google Ads webhook" ok={s.inbound.google_ads_webhook}
                    detail={s.inbound.google_ads_webhook ? "Receiving at /webhooks/google-ads" : "Disabled: set GIGSCOUT_GOOGLE_ADS_WEBHOOK_KEY"} />
                  <Check icon={<IconDatabase size={18} />} label="Database" ok detail={s.database.url} />
                  <Check icon={<IconServer size={18} />} label="MLflow tracking" ok={s.mlflow.enabled} detail={s.mlflow.tracking_uri} />
                </Stack>
              </Panel>
            </Grid.Col>
            <Grid.Col span={{ base: 12, lg: 7 }}>
              <Panel eyebrow="Last 30 days" title="Run reliability"
                actions={<Badge variant="light">{o ? `${o.runs_failed_7d} failed this week` : ""}</Badge>}>
                <Grid align="center">
                  <Grid.Col span={{ base: 12, sm: 4 }}>
                    <Center><Donut slices={runStatusSlices} caption="runs" size={170} /></Center>
                  </Grid.Col>
                  <Grid.Col span={{ base: 12, sm: 8 }}>
                    {analytics.data && <RunTimeline runs={analytics.data.runs} height={200} onSelect={(id) => navigate(`/runs/${id}`)} />}
                  </Grid.Col>
                </Grid>
              </Panel>
            </Grid.Col>
            <Grid.Col span={12}>
              <Panel eyebrow="Pipeline" title="Leads by stage">
                <Group gap="lg">
                  {Object.entries(o?.by_status ?? {}).map(([status, count]) => (
                    <Stack key={status} gap={2}>
                      <Group gap={6}>
                        <span className="gs-dot" style={{ background: STATUS_COLORS[status as keyof typeof STATUS_COLORS] }} />
                        <span className="gs-eyebrow">{status}</span>
                      </Group>
                      <Text className="gs-num" fz={26}>{count}</Text>
                    </Stack>
                  ))}
                </Group>
              </Panel>
            </Grid.Col>
          </Grid>
        </>
      )}
    </>
  );
}

function Check({ icon, label, ok, detail }: { icon: ReactNode; label: string; ok: boolean; detail: string }) {
  return (
    <Group wrap="nowrap" gap="sm" p="sm" style={{ background: "var(--gs-surface-2)", borderRadius: 12 }}>
      <ThemeIcon variant="light" radius="xl" color={ok ? "signal" : "orange"}>{icon}</ThemeIcon>
      <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
        <Text size="sm" fw={600}>{label}</Text>
        <Text size="xs" c="var(--gs-text-muted)" className="gs-mono" truncate>{detail}</Text>
      </Stack>
      <ThemeIcon size="sm" radius="xl" color={ok ? "signal" : "orange"} variant="filled">
        {ok ? <IconCheck size={12} /> : <IconX size={12} />}
      </ThemeIcon>
    </Group>
  );
}
