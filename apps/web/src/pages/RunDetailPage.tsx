import { Alert, Anchor, Badge, Grid, Group, SimpleGrid, Skeleton, Stack, Tabs, Text } from "@mantine/core";
import { IconAlertTriangle, IconArrowLeft, IconFileText, IconListDetails, IconTerminal2 } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import { Link, useParams } from "react-router";
import remarkGfm from "remark-gfm";

import { RunStatusBadge } from "../components/badges";
import { PageHeader, Panel, StatTile } from "../components/layout-bits";
import { RunConsole } from "../components/RunConsole";
import { api, messageOf } from "../lib/api";
import { dateTime, duration } from "../lib/format";
import { useRunLines } from "../lib/live";

export default function RunDetailPage() {
  const { runId = "" } = useParams();
  const run = useQuery({ queryKey: ["runs", "one", runId], queryFn: () => api.runs.get(runId) });
  const liveLines = useRunLines(runId);
  const r = run.data;
  const active = r?.status === "running" || r?.status === "queued";
  const consoleLines = active ? liveLines : (r?.trace ?? []).map((line) => ({ line }));

  return (
    <>
      <Anchor component={Link} to="/runs" size="sm" mb="sm" display="inline-block">
        <Group gap={4}>
          <IconArrowLeft size={14} /> All runs
        </Group>
      </Anchor>
      {run.isError && <Alert color="red">{messageOf(run.error)}</Alert>}
      {run.isPending && <Skeleton h={480} radius="lg" />}
      {r && (
        <>
          <PageHeader
            eyebrow={`Run · ${r.trigger} · ${r.triggered_by}`}
            title={r.profile_name}
            description={`Started ${dateTime(r.started_at ?? r.created_at)} · mode ${r.mode ?? r.mode_requested}`}
            actions={<RunStatusBadge status={r.status} />}
          />
          <SimpleGrid cols={{ base: 2, md: 4 }} mb="md" className="gs-stagger">
            <StatTile label="Fetched" value={r.fetched_count} />
            <StatTile label="New leads" value={r.new_count} />
            <StatTile label="Qualified" value={r.match_count} hint={r.top_score ? `top score ${r.top_score.toFixed(2)}` : undefined} />
            <StatTile label="Duration" value={duration(r.duration_seconds)} />
          </SimpleGrid>
          {r.errors.length > 0 && (
            <Alert color="orange" variant="light" icon={<IconAlertTriangle size={18} />} title={`${r.errors.length} warning(s)`} mb="md">
              <Stack gap={2}>
                {r.errors.map((e) => (
                  <Text key={e} size="sm" className="gs-mono">{e}</Text>
                ))}
              </Stack>
            </Alert>
          )}
          <Tabs defaultValue={active ? "console" : "briefing"} keepMounted={false}>
            <Tabs.List mb="md">
              <Tabs.Tab value="briefing" leftSection={<IconFileText size={16} />} disabled={!r.report}>Briefing</Tabs.Tab>
              <Tabs.Tab value="console" leftSection={<IconTerminal2 size={16} />}>Agent trace</Tabs.Tab>
              <Tabs.Tab value="queries" leftSection={<IconListDetails size={16} />}>Searches ({r.queries.length})</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="briefing">
              <Panel>
                <div className="gs-markdown">
                  <Markdown remarkPlugins={[remarkGfm]} components={{ a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}>
                    {r.report}
                  </Markdown>
                </div>
              </Panel>
            </Tabs.Panel>
            <Tabs.Panel value="console">
              <RunConsole lines={consoleLines} height={460} placeholder={active ? "Waiting for the agents…" : "No trace recorded."} />
            </Tabs.Panel>
            <Tabs.Panel value="queries">
              <Grid>
                <Grid.Col span={12}>
                  <Panel>
                    <Group gap="xs">
                      {r.queries.map((q) => (
                        <Badge key={q} variant="default" size="lg" style={{ textTransform: "none" }} className="gs-mono">{q}</Badge>
                      ))}
                    </Group>
                  </Panel>
                </Grid.Col>
              </Grid>
            </Tabs.Panel>
          </Tabs>
        </>
      )}
    </>
  );
}
