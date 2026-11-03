import { Box, Group, Progress, Stack, Text, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { Panel } from "../layout-bits";

const MAX_LIFT = 0.5;

/** What the team's won and lost leads have taught the scoring, as plain sentences with diverging bars. */
export function WhatWins() {
  const learning = useQuery({ queryKey: ["metrics", "learning"], queryFn: api.metrics.learning });
  const l = learning.data;

  return (
    <Panel eyebrow="Learning from outcomes" title="What wins for you">
      {!l ? null : !l.active ? (
        <Stack gap="sm">
          <Text size="sm">
            Mark leads <b>won</b> or <b>lost</b> in the pipeline and scoring starts favouring leads like your wins.
          </Text>
          <Progress value={(Math.min(l.outcomes, l.needed) / l.needed) * 100} color="signal" size="lg" radius="xl" />
          <Text size="xs" c="var(--gs-text-muted)">
            {l.outcomes} of {l.needed} outcomes recorded{l.outcomes >= l.needed ? " · needs at least one win and one loss" : ""}
          </Text>
        </Stack>
      ) : (
        <Stack gap={10}>
          <Text size="xs" c="var(--gs-text-muted)">
            From {l.wins} won and {l.losses} lost leads. Open leads like these move up or down by up to 15 points.
          </Text>
          {l.signals.length === 0 && <Text size="sm">No clear pattern yet: wins and losses look alike so far.</Text>}
          {l.signals.map((s) => (
            <Tooltip key={s.label} label={`${s.wins} won of ${s.total}`} position="top-start">
              <Box>
                <Group justify="space-between" gap="xs" wrap="nowrap">
                  <Text size="sm" truncate>{s.explain}</Text>
                  <Text size="xs" fw={600} c={s.lift > 0 ? "signal" : "orange"} className="gs-mono">
                    {s.lift > 0 ? "+" : ""}{Math.round(s.lift * 100)}
                  </Text>
                </Group>
                <Box pos="relative" h={6} mt={4} style={{ background: "var(--gs-line)", borderRadius: 3 }}>
                  <Box pos="absolute" top={0} h={6} style={{
                    borderRadius: 3,
                    left: s.lift >= 0 ? "50%" : `${50 - (Math.min(-s.lift, MAX_LIFT) / MAX_LIFT) * 50}%`,
                    width: `${(Math.min(Math.abs(s.lift), MAX_LIFT) / MAX_LIFT) * 50}%`,
                    background: s.lift > 0 ? "var(--mantine-color-signal-6)" : "var(--mantine-color-orange-6)",
                  }} />
                </Box>
              </Box>
            </Tooltip>
          ))}
        </Stack>
      )}
    </Panel>
  );
}
