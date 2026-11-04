import type { AgentKey, HoodStep } from "@gigscout/api-client";
import { AGENT_COLORS, AGENT_NAMES } from "@gigscout/viz";
import { Badge, Box, Chip, Group, Switch, Text, UnstyledButton } from "@mantine/core";
import { IconChevronRight } from "@tabler/icons-react";
import { type CSSProperties, useEffect, useRef } from "react";

import { OP_ICON, OP_LABEL } from "./ops";
import { AGENTS, millis, seconds, type Step } from "./steps";

interface StepTimelineProps {
  steps: Step[];
  showHood: boolean;
  onShowHood: (on: boolean) => void;
  agent: AgentKey | null;
  onAgent: (agent: AgentKey | null) => void;
  onOpen: (step: HoodStep) => void;
  live: boolean;
  height?: number;
}

/** The run, step by step. With "Under the hood" on, every AI call and tool call is listed and opens in detail. */
export function StepTimeline({ steps, showHood, onShowHood, agent, onAgent, onOpen, live, height = 480 }: StepTimelineProps) {
  const shown = steps.filter((s) => (showHood || !s.hood) && (agent === null || s.agent === agent));
  const hoodCount = steps.filter((s) => s.hood && (agent === null || s.agent === agent)).length;
  const end = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (live && follow.current) end.current?.scrollIntoView({ block: "nearest" });
  }, [shown.length, live]);

  return (
    <div>
      <Group justify="space-between" mb="sm" gap="sm">
        <Chip.Group multiple={false} value={agent ?? "all"} onChange={(v) => onAgent(v === "all" ? null : (v as AgentKey))}>
          <Group gap={6}>
            <Chip value="all" size="xs" variant="outline">All agents</Chip>
            {AGENTS.map((a) => <Chip key={a} value={a} size="xs" variant="outline" color={AGENT_COLORS[a]}>{AGENT_NAMES[a]}</Chip>)}
          </Group>
        </Chip.Group>
        <Switch checked={showHood} onChange={(e) => onShowHood(e.currentTarget.checked)} color="signal"
          label={<Text size="sm" fw={600}>Under the hood {hoodCount > 0 && <Badge size="xs" variant="light" ml={4}>{hoodCount}</Badge>}</Text>} />
      </Group>
      <Box className="gs-hood-timeline" h={height} role="log" aria-live={live ? "polite" : "off"}
        onScroll={(e) => {
          const el = e.currentTarget;
          follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}>
        {shown.length === 0 && (
          <Text size="sm" c="var(--gs-text-muted)" p="md">{live ? "Waiting for the agents…" : "Nothing recorded for this run."}</Text>
        )}
        {shown.map((s) => {
          const style = { "--agent": AGENT_COLORS[s.agent] } as CSSProperties;
          const body = (
            <>
              <span className="gs-hood-time">+{seconds(s.t)}</span>
              <span className="gs-hood-rail" />
              <div style={{ minWidth: 0, flex: 1 }}>
                <Group gap={6} wrap="nowrap">
                  <Text size="xs" fw={600} className="gs-hood-who">{AGENT_NAMES[s.agent]}</Text>
                  {s.hood && (
                    <Badge size="xs" variant="light" color="gray" leftSection={OP_ICON[s.hood.op]} className="gs-hood-op">
                      {OP_LABEL[s.hood.op]}
                    </Badge>
                  )}
                  {s.hood?.ms != null && <Text size="xs" c="var(--gs-text-muted)" className="gs-mono">{millis(s.hood.ms)}</Text>}
                </Group>
                <Text size="sm" lineClamp={2}>{s.text}</Text>
              </div>
              {s.hood && <IconChevronRight size={16} className="gs-hood-chevron" />}
            </>
          );
          return s.hood ? (
            <UnstyledButton key={s.key} className="gs-hood-row" data-hood data-tone={s.tone} style={style}
              onClick={() => onOpen(s.hood!)} aria-label={`Open details: ${s.text}`}>{body}</UnstyledButton>
          ) : (
            <div key={s.key} className="gs-hood-row" data-tone={s.tone} style={style}>{body}</div>
          );
        })}
        <div ref={end} />
      </Box>
      {!showHood && hoodCount > 0 && (
        <Text size="xs" c="var(--gs-text-muted)" mt="xs">
          {hoodCount} AI and tool steps are hidden. Turn on "Under the hood" to see each prompt, answer and tool call.
        </Text>
      )}
    </div>
  );
}
