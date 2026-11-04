import type { AgentKey, HoodStep } from "@gigscout/api-client";
import { AGENT_COLORS, AGENT_NAMES } from "@gigscout/viz";
import { Badge, Button, Drawer, Group, Loader, Stack, Text } from "@mantine/core";
import { IconArrowLeft } from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";

import { useRunActivity } from "../../lib/useRunActivity";
import { HoodDetail } from "./HoodDrawer";
import { StepTimeline } from "./StepTimeline";
import { AGENT_ROLE, agentStates, millis, toSteps } from "./steps";
import "./hood.css";

interface AgentHoodDrawerProps {
  runId: string | null;
  agent: AgentKey | null;
  active: boolean;
  onClose: () => void;
}

/** One agent's work on a run: every step it took, each AI or tool call opening to what went in and came out. */
export function AgentHoodDrawer({ runId, agent, active, onClose }: AgentHoodDrawerProps) {
  const { events, loading } = useRunActivity(agent ? runId : null, active);
  const [open, setOpen] = useState<HoodStep | null>(null);
  useEffect(() => setOpen(null), [agent]);
  const steps = useMemo(() => toSteps(events).filter((s) => s.agent === agent), [events, agent]);
  const state = agent ? agentStates(events, active)[agent] : null;

  return (
    <Drawer opened={agent !== null} onClose={onClose} position="right" size="lg"
      title={<span className="gs-eyebrow">Under the hood</span>}>
      {agent && state && (
        open ? (
          <Stack gap="md">
            <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={14} />} onClick={() => setOpen(null)} w="fit-content">
              All of {AGENT_NAMES[agent]}'s steps
            </Button>
            <HoodDetail step={open} />
          </Stack>
        ) : (
          <Stack gap="md">
            <div>
              <Group gap="xs" mb={4}>
                <Text fw={700} size="xl" className="gs-display" c={AGENT_COLORS[agent]}>{AGENT_NAMES[agent]}</Text>
                <Badge variant="light" color={AGENT_COLORS[agent]}>{state.status}</Badge>
              </Group>
              <Text size="sm" c="var(--gs-text-muted)">{AGENT_ROLE[agent]}</Text>
              {state.what && <Text size="sm" mt="xs">Now: <b>{state.what}</b></Text>}
            </div>
            <Group gap="lg" className="gs-hood-stats">
              <span>{state.aiCalls} AI calls</span>
              <span>{state.toolCalls} tool steps</span>
              {state.busyMs > 0 && <span>{millis(state.busyMs)} working</span>}
              {state.tokens > 0 && <span>{state.tokens.toLocaleString()} tokens</span>}
            </Group>
            {loading ? <Loader type="dots" /> : (
              <>
                <Text size="xs" c="var(--gs-text-muted)">Click any AI call or tool step to see exactly what went in and what came out.</Text>
                <StepTimeline bare steps={steps} showHood onShowHood={() => undefined} agent={agent} onAgent={() => undefined}
                  onOpen={setOpen} live={active} height={560} />
              </>
            )}
          </Stack>
        )
      )}
    </Drawer>
  );
}
