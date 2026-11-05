import type { PipelineStage, PipelineStep } from "@gigscout/api-client";
import { STAGE_COLORS, StageTrendChart } from "@gigscout/viz";
import { Alert, Anchor, Badge, Button, Chip, Grid, Group, SegmentedControl, Skeleton, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconReportAnalytics } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel } from "../components/layout-bits";
import { StageFlow } from "../components/pipeline/StageFlow";
import { StageLeads } from "../components/pipeline/StageLeads";
import { api, messageOf } from "../lib/api";
import { waitLabel } from "../lib/format";
import { RANGES, useDays } from "../lib/period";

const DEFAULT_LINES: PipelineStage[] = ["qualified", "drafted", "sent", "replied", "won"]; // "found" dwarfs the rest
const STALE_ADVICE: Partial<Record<PipelineStage, { text: string; to: string; action: string }>> = {
  drafted: { text: "pitches waiting for approval for more than 2 days", to: "/pitches", action: "Review pitches" },
  sent: { text: "sent with no reply for more than a week", to: "/leads?status=contacted", action: "Follow up" },
  replied: { text: "replies not moved forward for 3 days", to: "/leads?status=contacted", action: "Open leads" },
  proposal: { text: "proposals open for more than 2 weeks", to: "/leads?status=proposal", action: "Chase them" },
};

/** Every step from a lead being found to a deal being won, in one line, over time, with the leads behind each step. */
export default function PipelinePage() {
  const [days, setDays] = useDays();
  const [selected, setSelected] = useState<PipelineStage | null>(null);
  const [lines, setLines] = useState<string[]>(DEFAULT_LINES);
  const [openLead, setOpenLead] = useState<string | null>(null);
  const overview = useQuery({ queryKey: ["pipeline", "overview", days], queryFn: () => api.pipeline.overview(days) });
  const data = overview.data;
  const labels = Object.fromEntries((data?.stages ?? []).map((s) => [s.stage, s.label]));
  const stuck = (data?.stages ?? []).filter((s) => s.stale > 0 && STALE_ADVICE[s.stage]);

  return (
    <>
      <PageHeader eyebrow="Overview" title="Pipeline"
        description="Every step from a lead being found to a deal being won, connected. Click a step to see its leads."
        actions={
          <Group gap="xs">
            <SegmentedControl value={String(days)} onChange={setDays} data={RANGES.map((d) => ({ value: d, label: d === "365" ? "1y" : `${d}d` }))} />
            <Button variant="light" component={Link} to={`/reports?days=${days}`} leftSection={<IconReportAnalytics size={16} />}>Report</Button>
          </Group>
        } />
      {overview.isError && <Alert color="red" mb="md">{messageOf(overview.error)}</Alert>}
      <Stack gap="md">
        {data ? <StageFlow steps={data.stages} selected={selected} onSelect={(s) => setSelected((c) => (c === s ? null : s))} />
          : <Skeleton h={140} radius="md" />}

        {stuck.length > 0 && (
          <Alert variant="light" color="orange" icon={<IconAlertTriangle size={18} />} title="Leads waiting too long">
            <Stack gap={4}>
              {stuck.map((s) => (
                <Group key={s.stage} gap="xs">
                  <Text size="sm"><b className="gs-num">{s.stale}</b> {STALE_ADVICE[s.stage]!.text}</Text>
                  <Anchor component={Link} to={STALE_ADVICE[s.stage]!.to} size="sm">{STALE_ADVICE[s.stage]!.action}</Anchor>
                </Group>
              ))}
            </Stack>
          </Alert>
        )}

        {selected && <StageLeads stage={selected} days={days} onOpen={setOpenLead} />}

        <Grid gutter="md">
          <Grid.Col span={{ base: 12, lg: 8 }}>
            <Panel eyebrow={`Over time · ${days > 45 ? "per week" : "per day"}`} title="Leads reaching each step"
              actions={null}>
              <Chip.Group multiple value={lines} onChange={setLines}>
                <Group gap={6} mb="sm">
                  {(data?.stages ?? []).map((s) => (
                    <Chip key={s.stage} value={s.stage} size="xs" variant="light" color={STAGE_COLORS[s.stage]}>{s.label}</Chip>
                  ))}
                </Group>
              </Chip.Group>
              {data ? <StageTrendChart rows={data.series} stages={lines as PipelineStage[]} labels={labels} height={280} />
                : <Skeleton h={280} />}
            </Panel>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 4 }}>
            <Panel eyebrow="Speed" title="Where time goes">
              {data ? <SpeedList steps={data.stages} /> : <Skeleton h={240} />}
            </Panel>
          </Grid.Col>
        </Grid>
      </Stack>
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}

/** The median wait into each step as bars, so the slowest hand-off stands out. */
function SpeedList({ steps }: { steps: PipelineStep[] }) {
  const timed = steps.filter((s) => s.median_hours !== null);
  if (!timed.length) return <Text size="sm" c="var(--gs-text-muted)">Times show once leads move from one step to the next.</Text>;
  const slowest = Math.max(...timed.map((s) => s.median_hours!));
  return (
    <Stack gap="sm">
      {timed.map((s) => (
        <div key={s.stage}>
          <Group justify="space-between" gap="xs">
            <Text size="sm">{s.label}</Text>
            <Group gap={6}>
              {s.median_hours === slowest && timed.length > 1 && <Badge size="xs" color="orange" variant="light">slowest</Badge>}
              <Text size="sm" className="gs-num">{waitLabel(s.median_hours)}</Text>
            </Group>
          </Group>
          <div style={{ height: 6, borderRadius: 3, background: "var(--gs-surface-2)", marginTop: 4 }}>
            <div style={{ height: 6, borderRadius: 3, width: `${Math.max(4, (s.median_hours! / slowest) * 100)}%`, background: STAGE_COLORS[s.stage] }} />
          </div>
        </div>
      ))}
      <Text size="xs" c="var(--gs-text-dim)">Median time from the step before.</Text>
    </Stack>
  );
}
