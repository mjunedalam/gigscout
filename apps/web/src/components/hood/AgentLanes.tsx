import type { AgentKey } from "@gigscout/api-client";
import { AGENT_COLORS, AGENT_NAMES } from "@gigscout/viz";
import { Group, Progress, SimpleGrid, Text, UnstyledButton } from "@mantine/core";
import { IconBrain, IconFileText, IconSearch, IconTarget } from "@tabler/icons-react";
import type { CSSProperties, ReactNode } from "react";

import { AGENT_ROLE, AGENTS, type AgentState, millis } from "./steps";

const ICON: Record<AgentKey, ReactNode> = {
  head: <IconBrain size={18} />,
  prospector: <IconSearch size={18} />,
  qualifier: <IconTarget size={18} />,
  writer: <IconFileText size={18} />,
};
const STATUS_TEXT = { waiting: "Waiting", working: "Working", done: "Done" } as const;

interface AgentLanesProps {
  states: Record<AgentKey, AgentState>;
  /** Clicking a card opens that agent's under-the-hood steps. */
  onPeek?: (agent: AgentKey) => void;
  compact?: boolean;
}

/** One card per agent: what it is doing right now, how far along, and how much work it has done. */
export function AgentLanes({ states, onPeek, compact = false }: AgentLanesProps) {
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="sm">
      {AGENTS.map((agent) => {
        const s = states[agent];
        const pct = s.progress ? Math.min(100, (s.progress.done / Math.max(1, s.progress.total)) * 100) : 0;
        return (
          <UnstyledButton key={agent} className="gs-hood-agent" data-status={s.status} onClick={() => onPeek?.(agent)}
            style={{ "--agent": AGENT_COLORS[agent] } as CSSProperties}
            aria-label={`${AGENT_NAMES[agent]}: ${STATUS_TEXT[s.status]}. Show what happens under the hood`}>
            <Group justify="space-between" wrap="nowrap" gap="xs">
              <Group gap={10} wrap="nowrap" style={{ minWidth: 0 }}>
                <span className="gs-hood-avatar">{ICON[agent]}</span>
                <div style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>{AGENT_NAMES[agent]}</Text>
                  {!compact && <Text size="xs" c="var(--gs-text-muted)" truncate>{AGENT_ROLE[agent]}</Text>}
                </div>
              </Group>
              <span className="gs-hood-status"><span className="gs-hood-dot" />{STATUS_TEXT[s.status]}</span>
            </Group>
            <Text size="sm" mt="sm" className="gs-hood-what" lineClamp={2}>
              {s.what || (s.status === "waiting" ? "Waiting for its turn" : "…")}
            </Text>
            <Progress value={s.status === "done" && s.progress === null ? 100 : pct} size={4} mt="sm" radius="xl"
              color={AGENT_COLORS[agent]} animated={s.status === "working"} aria-hidden />
            <Group gap="md" mt={8} className="gs-hood-stats">
              <span>{s.aiCalls} AI calls</span>
              <span>{s.toolCalls} tool steps</span>
              {s.busyMs > 0 && <span>{millis(s.busyMs)}</span>}
              {!compact && s.tokens > 0 && <span>{s.tokens.toLocaleString()} tokens</span>}
            </Group>
          </UnstyledButton>
        );
      })}
    </SimpleGrid>
  );
}
