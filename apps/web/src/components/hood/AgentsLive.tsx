import type { AgentKey, HoodStep } from "@gigscout/api-client";
import { Alert, Skeleton, Stack } from "@mantine/core";
import { useMemo, useState } from "react";

import { useRunActivity } from "../../lib/useRunActivity";
import { AgentLanes } from "./AgentLanes";
import { HoodDrawer } from "./HoodDrawer";
import { StepTimeline } from "./StepTimeline";
import { agentStates, toSteps } from "./steps";
import "./hood.css";

/** What every agent is doing, step by step, with each AI call and tool call one click away. */
export function AgentsLive({ runId, active }: { runId: string; active: boolean }) {
  const { events, loading, error } = useRunActivity(runId, active);
  const states = useMemo(() => agentStates(events, active), [events, active]);
  const steps = useMemo(() => toSteps(events), [events]);
  const [showHood, setShowHood] = useState(false);
  const [agent, setAgent] = useState<AgentKey | null>(null);
  const [open, setOpen] = useState<HoodStep | null>(null);

  if (error) return <Alert color="red">{error}</Alert>;
  if (loading) return <Skeleton h={420} radius="lg" />;
  return (
    <Stack gap="lg">
      <AgentLanes states={states} onPeek={(a) => { setAgent(a); setShowHood(true); }} />
      <StepTimeline steps={steps} showHood={showHood} onShowHood={setShowHood} agent={agent} onAgent={setAgent}
        onOpen={setOpen} live={active} />
      <HoodDrawer step={open} onClose={() => setOpen(null)} />
    </Stack>
  );
}

/** Just the agent cards, for a page that links to the full view. */
export function AgentLanesLive({ runId, onPeek }: { runId: string; onPeek?: (agent: AgentKey) => void }) {
  const { events } = useRunActivity(runId, true);
  const states = useMemo(() => agentStates(events, true), [events]);
  return <AgentLanes states={states} onPeek={onPeek} compact />;
}
