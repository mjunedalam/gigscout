import { LEAD_KINDS } from "@gigscout/api-client";
import { Donut, KIND_COLORS, KIND_LABELS, LeadFlowChart } from "@gigscout/viz";
import { Badge, Button, Center, Grid, Group, Loader, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconBolt, IconCircleCheck, IconMailbox, IconRadar2, IconStack2 } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { Link } from "react-router";

import { ActivityFeed } from "../components/ActivityFeed";
import { RunStatusBadge } from "../components/badges";
import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel, StatTile } from "../components/layout-bits";
import { RunConsole } from "../components/RunConsole";
import { StartRunButton } from "../components/StartRunButton";
import { api } from "../lib/api";
import { duration, timeAgo } from "../lib/format";
import { useLive, useRunLines } from "../lib/live";

const LeadGalaxy = lazy(() => import("@gigscout/viz/galaxy"));

export default function CommandCenterPage() {
  const live = useLive();
  const [openLead, setOpenLead] = useState<string | null>(null);
  const overview = useQuery({ queryKey: ["metrics", "overview"], queryFn: api.metrics.overview });
  const analytics = useQuery({ queryKey: ["metrics", "analytics", 14], queryFn: () => api.metrics.analytics(14) });
  const map = useQuery({ queryKey: ["metrics", "map"], queryFn: api.metrics.map, staleTime: 120_000 });
  const o = overview.data;
  const activeRun = o?.active_runs.find((r) => r.status === "running") ?? o?.active_runs[0];
  const lines = useRunLines(activeRun?.id);

  return (
    <>
      <PageHeader
        eyebrow="Command center · live"
        title="Where your next clients are"
        description="Every lead the agents found, every enquiry your ads brought in, updating as it happens."
        actions={<StartRunButton />}
      />

      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md" className="gs-stagger" mb="md">
        <StatTile label="Leads in memory" value={o?.total_leads ?? "–"} hint={`${o?.new_last_24h ?? 0} new in 24h`}
          icon={<IconStack2 size={20} />} trend={live.history.totalLeads} />
        <StatTile label="Qualified" value={o?.qualified ?? "–"} hint="Score ≥ threshold, ready to pitch"
          icon={<IconCircleCheck size={20} />} trend={live.history.qualified} />
        <StatTile label="Inbound · 7 days" value={o?.inbound_last_7d ?? "–"} hint="From Google Ads lead forms"
          icon={<IconMailbox size={20} />} accent={KIND_COLORS.inbound} />
        <StatTile label="Runs · 7 days" value={o ? `${o.runs_succeeded_7d}/${o.runs_succeeded_7d + o.runs_failed_7d}` : "–"}
          hint={`avg ${duration(o?.avg_run_seconds)} · last ${timeAgo(o?.last_run_at)}`}
          icon={<IconBolt size={20} />} accent={KIND_COLORS.contract} trend={live.history.activeRuns} />
      </SimpleGrid>

      <Grid gutter="md" mb="md">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Panel hero eyebrow="Lead galaxy · drag to orbit" title="Leads clustered by meaning"
            actions={<Group gap="sm" visibleFrom="sm">{LEAD_KINDS.map((k) => (
              <Group key={k} gap={4}><span className="gs-dot" style={{ background: KIND_COLORS[k] }} />
                <Text size="xs" c="var(--gs-text-muted)">{KIND_LABELS[k]}</Text></Group>))}</Group>}>
            {map.data && map.data.length > 0 ? (
              <Suspense fallback={<Center h={420}><Loader type="dots" /></Center>}>
                <LeadGalaxy points={map.data} height={420} onSelect={setOpenLead} />
              </Suspense>
            ) : (
              <Center h={420}>
                <Stack align="center" gap="xs">
                  <IconRadar2 size={42} stroke={1.2} />
                  <Text c="var(--gs-text-muted)" size="sm">{map.isPending ? "Mapping your leads…" : "Run the agents to light up the galaxy."}</Text>
                </Stack>
              </Center>
            )}
          </Panel>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Panel eyebrow="Live activity" title="What just happened" padding={20}>
            <ActivityFeed events={live.feed} height={420} />
          </Panel>
        </Grid.Col>
      </Grid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Panel eyebrow="Lead flow · 14 days" title="New leads per day, by kind"
            actions={<Button component={Link} to="/analytics" variant="subtle" size="xs">Analytics →</Button>}>
            {analytics.data ? <LeadFlowChart rows={analytics.data.timeseries} height={260} /> : <Center h={260}><Loader type="dots" /></Center>}
          </Panel>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Panel eyebrow="Sources" title="Where leads come from">
            <Center>
              <Donut caption="leads" size={210} slices={Object.entries(o?.by_source ?? {}).map(([key, value], i) => ({
                key, label: key, value, color: SOURCE_TINTS[i % SOURCE_TINTS.length]!,
              }))} />
            </Center>
            <Group gap="xs" mt="md" justify="center">
              {Object.entries(o?.by_source ?? {}).map(([name, count], i) => (
                <Badge key={name} variant="default" leftSection={<span className="gs-dot" style={{ background: SOURCE_TINTS[i % SOURCE_TINTS.length] }} />}>
                  {name} · {count}
                </Badge>
              ))}
            </Group>
          </Panel>
        </Grid.Col>
        {activeRun && (
          <Grid.Col span={12}>
            <Panel eyebrow="Agents at work" title={activeRun.profile_name} actions={<RunStatusBadge status={activeRun.status} />}>
              <RunConsole lines={lines} height={220} />
              <Button component={Link} to={`/runs/${activeRun.id}`} variant="subtle" size="xs" mt="sm">Open run →</Button>
            </Panel>
          </Grid.Col>
        )}
      </Grid>
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}

const SOURCE_TINTS = ["#C6F432", "#8B7CFF", "#2DD4BF", "#F5B544", "#FF6B8B", "#5AA9FF", "#B794F6"];
