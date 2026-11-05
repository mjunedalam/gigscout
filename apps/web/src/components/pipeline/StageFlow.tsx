import type { PipelineStage, PipelineStep } from "@gigscout/api-client";
import { STAGE_COLORS } from "@gigscout/viz";
import { Badge, Box, Group, SimpleGrid, Text, Tooltip, UnstyledButton } from "@mantine/core";
import { IconArrowDownRight, IconArrowUpRight, IconChevronRight, IconClockHour4 } from "@tabler/icons-react";

import { change, waitLabel } from "../../lib/format";
import "./pipeline.css";

interface StageFlowProps {
  steps: PipelineStep[];
  selected: PipelineStage | null;
  onSelect: (stage: PipelineStage) => void;
}

/** Every pipeline step in one connected line. Each card: how many leads got there, the change from the period
 * before, the conversion from the step before, and how long that took. Click one to see its leads. */
export function StageFlow({ steps, selected, onSelect }: StageFlowProps) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 4, xl: 8 }} spacing={0} className="gs-flow" role="group" aria-label="Pipeline steps">
      {steps.map((step, i) => (
        <StageCard key={step.stage} step={step} first={i === 0} active={selected === step.stage}
          onClick={() => onSelect(step.stage)} />
      ))}
    </SimpleGrid>
  );
}

function StageCard({ step, first, active, onClick }: { step: PipelineStep; first: boolean; active: boolean; onClick: () => void }) {
  const delta = change(step.count, step.previous);
  const color = STAGE_COLORS[step.stage];
  const exit = step.stage === "lost";
  return (
    <UnstyledButton className="gs-flow-step" data-active={active || undefined} data-exit={exit || undefined}
      onClick={onClick} aria-pressed={active} aria-label={`${step.label}: ${step.count} leads, show them`} style={{ ["--stage" as string]: color }}>
      {!first && !exit && (
        <Tooltip label="Of the leads at the step before, this share got here">
          <span className="gs-flow-link">
            <IconChevronRight size={12} />
            {step.conversion !== null ? `${Math.round(step.conversion * 100)}%` : "—"}
          </span>
        </Tooltip>
      )}
      <Text className="gs-eyebrow" style={{ color }}>{step.label}</Text>
      <Group gap={6} align="baseline" wrap="nowrap">
        <Text className="gs-num" fz={30} fw={500} lh={1.1}>{step.count}</Text>
        {delta !== null && delta !== 0 && (
          <Text size="xs" c={(delta > 0) !== exit ? "teal" : "red"} fw={600} className="gs-num">
            {delta > 0 ? <IconArrowUpRight size={12} /> : <IconArrowDownRight size={12} />}
            {Math.abs(delta)}%
          </Text>
        )}
      </Group>
      <Group gap={4} mt={4} wrap="nowrap" mih={18}>
        {step.median_hours !== null && (
          <>
            <IconClockHour4 size={12} color="var(--gs-text-muted)" />
            <Text size="xs" c="var(--gs-text-muted)">{waitLabel(step.median_hours)} to get here</Text>
          </>
        )}
      </Group>
      <Box mt={6} mih={20}>
        {step.waiting > 0 && !exit && step.stage !== "won" && (
          <Badge size="xs" variant="light" color={step.stale ? "orange" : "gray"}>
            {step.waiting} here now{step.stale ? ` · ${step.stale} stuck` : ""}
          </Badge>
        )}
      </Box>
    </UnstyledButton>
  );
}
