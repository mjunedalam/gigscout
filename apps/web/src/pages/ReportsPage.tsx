import type { OwnerReport, PipelineStage } from "@gigscout/api-client";
import { STAGE_COLORS, StageTrendChart } from "@gigscout/viz";
import { Alert, Button, Grid, Group, SegmentedControl, SimpleGrid, Skeleton, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCash, IconFileSpreadsheet, IconMessageReply, IconPrinter, IconSend, IconTrophy } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel, StatTile } from "../components/layout-bits";
import { AnalystPanel } from "../components/pipeline/AnalystPanel";
import { api, messageOf } from "../lib/api";
import { change, dateTime, usd, waitLabel } from "../lib/format";
import { RANGES, useDays } from "../lib/period";

const TREND: PipelineStage[] = ["qualified", "sent", "replied", "won"];
const AGENTS = "GigScout agents";

/** The owner's report: what came in, what went out, what was won, and which sources and people made it happen. */
export default function ReportsPage() {
  const [days, setDays] = useDays();
  const [openLead, setOpenLead] = useState<string | null>(null);
  const report = useQuery({ queryKey: ["reports", "owner", days], queryFn: () => api.reports.owner(days) });
  const r = report.data;

  const downloadCsv = async () => {
    try {
      const blob = await api.reports.ownerCsv(days);
      const url = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement("a"), { href: url, download: `gigscout-report-${days}d.csv` });
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notifications.show({ color: "red", title: "Could not download", message: messageOf(e) });
    }
  };

  return (
    <>
      <PageHeader eyebrow="Intelligence" title="Owner report"
        description={r ? `${r.workspace} · ${dateTime(r.start)} to ${dateTime(r.end)}` : "Revenue, pipeline, sources and team for a period."}
        actions={
          <Group gap="xs" className="gs-no-print">
            <SegmentedControl value={String(days)} onChange={setDays} data={RANGES.map((d) => ({ value: d, label: d === "365" ? "1y" : `${d}d` }))} />
            <Button variant="light" leftSection={<IconFileSpreadsheet size={16} />} onClick={downloadCsv}>CSV</Button>
            <Button variant="light" leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Print / PDF</Button>
          </Group>
        } />
      {report.isError && <Alert color="red" mb="md">{messageOf(report.error)}</Alert>}
      {!r ? <Skeleton h={480} radius="md" /> : <ReportBody r={r} onOpen={setOpenLead} />}
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}

function ReportBody({ r, onOpen }: { r: OwnerReport; onOpen: (id: string) => void }) {
  const step = (s: PipelineStage) => r.stages.find((x) => x.stage === s)!;
  const sent = step("sent"), replied = step("replied");
  const replyRate = sent.count ? replied.count / sent.count : null;
  const revenueChange = change(r.revenue.won, r.revenue.previous);
  const labels = Object.fromEntries(r.stages.map((s) => [s.stage, s.label]));

  return (
    <Stack gap="md" className="gs-report">
      <AnalystPanel days={r.days} />
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        <StatTile label="Revenue won" value={usd(r.revenue.won, r.revenue.won >= 100_000)} icon={<IconCash size={20} />}
          hint={revenueHint(r.revenue.won, r.revenue.previous, revenueChange)} />
        <StatTile label="Deals won" value={r.revenue.deals} icon={<IconTrophy size={20} />} accent={STAGE_COLORS.won}
          hint={r.revenue.valued ? `avg ${usd(r.revenue.won / r.revenue.valued)} · ${r.revenue.deals - r.revenue.valued} without a value` : "Add a deal value when you mark a lead won"} />
        <StatTile label="Reply rate" value={replyRate === null ? "—" : `${Math.round(replyRate * 100)}%`} icon={<IconMessageReply size={20} />}
          accent={STAGE_COLORS.replied} hint={`${replied.count} replies to ${sent.count} sent`} />
        <StatTile label="Pitches approved" value={r.pitches.approval_rate === null ? "—" : `${Math.round(r.pitches.approval_rate * 100)}%`}
          icon={<IconSend size={20} />} accent={STAGE_COLORS.drafted}
          hint={`${r.pitches.approved} of ${r.pitches.approved + r.pitches.rejected} reviewed · median ${waitLabel(r.pitches.median_review_hours)} to review`} />
      </SimpleGrid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Panel eyebrow="Pipeline" title="Step by step, against the period before">
            <Table.ScrollContainer minWidth={520}>
              <Table verticalSpacing={6}>
                <Table.Thead><Table.Tr>
                  <Table.Th>Step</Table.Th><Table.Th ta="right">Leads</Table.Th><Table.Th ta="right">Before</Table.Th>
                  <Table.Th ta="right">Conversion</Table.Th><Table.Th ta="right">Wait</Table.Th><Table.Th ta="right">Open now</Table.Th>
                </Table.Tr></Table.Thead>
                <Table.Tbody>
                  {r.stages.map((s) => (
                    <Table.Tr key={s.stage}>
                      <Table.Td><Group gap={6}><span className="gs-dot" style={{ background: STAGE_COLORS[s.stage] }} />{s.label}</Group></Table.Td>
                      <Table.Td ta="right" className="gs-num" fw={600}>{s.count}</Table.Td>
                      <Table.Td ta="right" className="gs-num" c="var(--gs-text-muted)">{s.previous}</Table.Td>
                      <Table.Td ta="right" className="gs-num">{s.conversion === null ? "—" : `${Math.round(s.conversion * 100)}%`}</Table.Td>
                      <Table.Td ta="right" className="gs-num">{waitLabel(s.median_hours)}</Table.Td>
                      <Table.Td ta="right" className="gs-num">{s.stage === "won" || s.stage === "lost" ? "—" : s.waiting}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Panel>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Panel eyebrow={r.days > 45 ? "Per week" : "Per day"} title="Momentum">
            <StageTrendChart rows={r.series} stages={TREND} labels={labels} height={250} />
            <Group gap="md" mt="xs">
              {TREND.map((s) => <Group key={s} gap={4}><span className="gs-dot" style={{ background: STAGE_COLORS[s] }} /><Text size="xs">{labels[s]}</Text></Group>)}
            </Group>
          </Panel>
        </Grid.Col>
      </Grid>

      <Panel eyebrow="Sources" title="Where the business comes from">
        {r.sources.length === 0 ? <Text size="sm" c="var(--gs-text-muted)">No leads in this period.</Text> : (
          <Table.ScrollContainer minWidth={640}>
            <Table verticalSpacing={6} striped>
              <Table.Thead><Table.Tr>
                <Table.Th>Source</Table.Th><Table.Th ta="right">Found</Table.Th><Table.Th ta="right">Qualified</Table.Th>
                <Table.Th ta="right">Sent</Table.Th><Table.Th ta="right">Reply rate</Table.Th><Table.Th ta="right">Won</Table.Th>
                <Table.Th ta="right">Won value</Table.Th>
              </Table.Tr></Table.Thead>
              <Table.Tbody>
                {r.sources.slice(0, 15).map((s) => (
                  <Table.Tr key={s.source}>
                    <Table.Td>{s.source}</Table.Td>
                    <Table.Td ta="right" className="gs-num">{s.found}</Table.Td>
                    <Table.Td ta="right" className="gs-num">{s.qualified}</Table.Td>
                    <Table.Td ta="right" className="gs-num">{s.sent}</Table.Td>
                    <Table.Td ta="right" className="gs-num">{s.reply_rate === null ? "—" : `${Math.round(s.reply_rate * 100)}%`}</Table.Td>
                    <Table.Td ta="right" className="gs-num">{s.won}</Table.Td>
                    <Table.Td ta="right" className="gs-num" fw={600}>{s.won_value ? usd(s.won_value) : "—"}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Panel>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Panel eyebrow="Team" title="Who moved leads forward">
            {r.people.length === 0 ? <Text size="sm" c="var(--gs-text-muted)">Nobody moved a lead in this period.</Text> : (
              <Table.ScrollContainer minWidth={520}>
                <Table verticalSpacing={6}>
                  <Table.Thead><Table.Tr>
                    <Table.Th>Who</Table.Th><Table.Th ta="right">Drafted</Table.Th><Table.Th ta="right">Sent</Table.Th>
                    <Table.Th ta="right">Replies</Table.Th><Table.Th ta="right">Won</Table.Th><Table.Th ta="right">Lost</Table.Th>
                  </Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {r.people.map((p) => (
                      <Table.Tr key={p.actor}>
                        <Table.Td>{p.actor === AGENTS ? "The agents" : p.actor}</Table.Td>
                        <Table.Td ta="right" className="gs-num">{p.drafted}</Table.Td>
                        <Table.Td ta="right" className="gs-num">{p.sent}</Table.Td>
                        <Table.Td ta="right" className="gs-num">{p.replied}</Table.Td>
                        <Table.Td ta="right" className="gs-num" fw={600}>{p.won}</Table.Td>
                        <Table.Td ta="right" className="gs-num">{p.lost}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Panel>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Panel eyebrow="Agents" title="What the automation did">
            <Stack gap={6}>
              <Fact label="Runs" value={`${r.runs.succeeded} ok · ${r.runs.failed} failed`} />
              <Fact label="Listings read" value={r.runs.leads_fetched} />
              <Fact label="New leads" value={r.runs.new_leads} />
              <Fact label="Pitches drafted by the agents" value={`${r.pitches.by_agents} of ${r.pitches.drafted}`} />
              <Fact label="Waiting for approval" value={r.pitches.waiting} />
            </Stack>
          </Panel>
        </Grid.Col>
      </Grid>

      <Panel eyebrow="Wins" title="Deals won in the period">
        {r.wins.length === 0 ? <Text size="sm" c="var(--gs-text-muted)">No wins yet in this period.</Text> : (
          <Stack gap={6}>
            {r.wins.map((w) => (
              <Group key={w.id} justify="space-between" wrap="nowrap" gap="sm">
                <Text size="sm" lineClamp={1} style={{ cursor: "pointer" }} onClick={() => onOpen(w.id)}>{w.title}</Text>
                <Group gap="sm" wrap="nowrap">
                  <Text size="xs" c="var(--gs-text-muted)">{w.source}</Text>
                  <Text size="sm" className="gs-num" fw={600}>{usd(w.deal_value_usd)}</Text>
                </Group>
              </Group>
            ))}
          </Stack>
        )}
      </Panel>
    </Stack>
  );
}

function revenueHint(won: number, previous: number, delta: number | null): string {
  if (!won && !previous) return "No revenue in this or the period before";
  if (delta === null) return `Nothing the period before`;
  return `${delta >= 0 ? "+" : ""}${delta}% vs. ${usd(previous)} the period before`;
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <Group justify="space-between">
      <Text size="sm" c="var(--gs-text-muted)">{label}</Text>
      <Text size="sm" className="gs-num">{value}</Text>
    </Group>
  );
}
