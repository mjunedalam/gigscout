import { CompetitionScatter, LeadFlowChart, PipelineFunnel, RunTimeline, ScoreHistogram } from "@gigscout/viz";
import { Alert, Grid, SegmentedControl } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { WhatWins } from "../components/analytics/WhatWins";
import { MarketTrends } from "../components/analytics/MarketTrends";
import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel } from "../components/layout-bits";
import { api, messageOf } from "../lib/api";
import { ChartsSkeleton } from "../components/skeletons";

const RANGES = ["7", "14", "30", "90"];

export default function AnalyticsPage() {
  const [days, setDays] = useState("30");
  const [openLead, setOpenLead] = useState<string | null>(null);
  const navigate = useNavigate();
  const analytics = useQuery({
    queryKey: ["metrics", "analytics", Number(days)],
    queryFn: () => api.metrics.analytics(Number(days)),
  });
  const a = analytics.data;

  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title="Analytics"
        description="Which leads are worth it, how crowded the market is, and how your pipeline converts."
        actions={<SegmentedControl value={days} onChange={setDays} data={RANGES.map((d) => ({ value: d, label: `${d}d` }))} />}
      />
      {analytics.isError && <Alert color="red">{messageOf(analytics.error)}</Alert>}
      {!a ? (
        <ChartsSkeleton />
      ) : (
        <Grid gutter="md" className="gs-stagger">
          <Grid.Col span={12}>
            <MarketTrends />
          </Grid.Col>
          <Grid.Col span={12}>
            <Panel eyebrow={`Lead flow · ${days} days`} title="New leads per day, by kind">
              <LeadFlowChart rows={a.timeseries} height={280} />
            </Panel>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <Panel eyebrow="Competition" title="Budget vs. competing bids">
              <CompetitionScatter points={a.competition} height={320} onSelect={setOpenLead} />
            </Panel>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Panel eyebrow="Qualification" title="Score distribution">
              <ScoreHistogram bins={a.score_histogram} height={320} />
            </Panel>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Panel eyebrow="Sales pipeline" title="Funnel and conversion">
              <PipelineFunnel stages={a.funnel} />
            </Panel>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <WhatWins />
          </Grid.Col>
          <Grid.Col span={12}>
            <Panel eyebrow={`Last ${a.runs.length} runs`} title="Run duration and new leads">
              <RunTimeline runs={a.runs} height={240} onSelect={(id) => navigate(`/runs/${id}`)} />
            </Panel>
          </Grid.Col>
        </Grid>
      )}
      <LeadDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </>
  );
}
