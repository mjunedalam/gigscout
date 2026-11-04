import type { TrendRow } from "@gigscout/api-client";
import { Sparkline } from "@gigscout/viz";
import { Badge, Box, Grid, Group, SegmentedControl, Skeleton, Stack, Text, Tooltip } from "@mantine/core";
import { IconArrowDownRight, IconArrowUpRight, IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../lib/api";
import { Panel } from "../layout-bits";

const pct = (change: number | null) => (change === null ? "new" : `${change > 0 ? "+" : ""}${Math.round(change * 100)}%`);
const usd = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : `$${Math.round(v)}`);

/** What the market asks for, and how fast it is moving: from every lead this workspace has seen. */
export function MarketTrends() {
  const [weeks, setWeeks] = useState("4");
  const trends = useQuery({ queryKey: ["metrics", "trends", weeks], queryFn: () => api.metrics.trends(Number(weeks)) });
  const t = trends.data;
  const top = Math.max(1, ...(t?.demand ?? []).map((r) => Math.max(r.recent, r.previous)));

  return (
    <Panel eyebrow="Market trends" title="What clients are asking for"
      actions={<SegmentedControl size="xs" value={weeks} onChange={setWeeks}
        data={[{ value: "2", label: "2 wk" }, { value: "4", label: "4 wk" }, { value: "8", label: "8 wk" }]} />}>
      {!t ? <Skeleton h={260} /> : t.demand.length === 0 ? (
        <Text size="sm" c="var(--gs-text-muted)">Not enough leads yet: trends appear after a few runs.</Text>
      ) : (
        <Grid gutter="xl">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Text size="xs" c="var(--gs-text-muted)" mb="xs">Mentions in the last {t.weeks} weeks (bar) against the {t.weeks} before (tick)</Text>
            <Stack gap={8}>
              {t.demand.map((r) => <DemandRow key={r.term} row={r} top={top} />)}
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Stack gap="lg">
              <Movers title="Rising" rows={t.rising} up />
              <Movers title="Cooling" rows={t.falling} />
              {t.new.length > 0 && (
                <div>
                  <span className="gs-eyebrow">New this period</span>
                  <Group gap={6} mt={6}>{t.new.map((r) => <Badge key={r.term} variant="light" color="teal" tt="none" leftSection={<IconSparkles size={10} />}>{r.term} · {r.recent}</Badge>)}</Group>
                </div>
              )}
              {t.budgets.length > 1 && (
                <div>
                  <span className="gs-eyebrow">Median project budget, by week</span>
                  <Group gap="md" mt={6} wrap="nowrap">
                    <Sparkline values={t.budgets.map((b) => b.median_usd)} width={180} height={40} label="Median project budget per week" />
                    <Text className="gs-num" fw={600}>{usd(t.budgets.at(-1)!.median_usd)}</Text>
                  </Group>
                </div>
              )}
            </Stack>
          </Grid.Col>
        </Grid>
      )}
    </Panel>
  );
}

function DemandRow({ row, top }: { row: TrendRow; top: number }) {
  const up = row.change === null || row.change > 0;
  return (
    <Group gap="sm" wrap="nowrap">
      <Text size="sm" w={150} truncate fw={row.yours ? 700 : 500} title={row.term}>
        {row.term}{row.yours && <Tooltip label="One of your skills or services"><span> ★</span></Tooltip>}
      </Text>
      <Box style={{ flex: 1, position: "relative", height: 10, borderRadius: 5, background: "var(--gs-btn-soft)" }}>
        <Box style={{ position: "absolute", inset: 0, width: `${(row.recent / top) * 100}%`, borderRadius: 5, background: row.yours ? "var(--gs-signal)" : "var(--gs-project)" }} />
        <Box style={{ position: "absolute", top: -3, bottom: -3, left: `calc(${(row.previous / top) * 100}% - 1px)`, width: 2, background: "var(--gs-text-muted)" }} />
      </Box>
      <Text size="xs" className="gs-num" w={36} ta="right">{row.recent}</Text>
      <Text size="xs" className="gs-num" w={48} ta="right" c={row.change === null ? "teal" : up ? "signal" : "orange"}>{pct(row.change)}</Text>
    </Group>
  );
}

function Movers({ title, rows, up = false }: { title: string; rows: TrendRow[]; up?: boolean }) {
  if (!rows.length) return null;
  return (
    <div>
      <span className="gs-eyebrow">{title}</span>
      <Stack gap={4} mt={6}>
        {rows.map((r) => (
          <Group key={r.term} justify="space-between" wrap="nowrap">
            <Group gap={6} wrap="nowrap">
              {up ? <IconArrowUpRight size={14} color="var(--gs-signal)" /> : <IconArrowDownRight size={14} color="var(--mantine-color-orange-5)" />}
              <Text size="sm" truncate>{r.term}</Text>
            </Group>
            <Text size="xs" className="gs-num" c="var(--gs-text-muted)">{r.previous} → {r.recent} ({pct(r.change)})</Text>
          </Group>
        ))}
      </Stack>
    </div>
  );
}
