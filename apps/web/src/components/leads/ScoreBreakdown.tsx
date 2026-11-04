import type { LeadView } from "@gigscout/api-client";
import { Box, Group, Stack, Text, Tooltip } from "@mantine/core";

const pts = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v * 100))}`;

/** Why this score: every ingredient, its weight and what it added, then what won/lost leads taught. */
export function ScoreBreakdown({ view }: { view: LeadView }) {
  const parts = view.score_parts ?? [];
  if (!parts.length || view.score === null) return null;
  const learned = view.learned ?? 0;
  const top = Math.max(0.01, ...parts.map((p) => Math.abs(p.points)), Math.abs(learned));
  const rows = [
    ...parts.map((p) => ({ key: p.key, label: p.label, points: p.points,
      detail: p.weight ? `${Math.round(p.value * 100)}% × weight ${Math.round(p.weight * 100)}%` : "adjustment" })),
    ...(learned ? [{ key: "learned", label: "Learned from your won and lost leads", points: learned, detail: view.learned_note || "" }] : []),
  ];
  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <span className="gs-eyebrow">Why this score</span>
        <Text size="xs" className="gs-num" c="var(--gs-text-muted)">{Math.round(view.score * 100)} points in total</Text>
      </Group>
      {rows.map((r) => (
        <Tooltip key={r.key} label={r.detail} disabled={!r.detail} multiline w={280} position="top-start">
          <Group gap="sm" wrap="nowrap">
            <Text size="xs" w={210} lineClamp={1}>{r.label}</Text>
            <Box style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--gs-btn-soft)", position: "relative" }}>
              <Box style={{ position: "absolute", top: 0, bottom: 0, left: 0, borderRadius: 4, width: `${(Math.abs(r.points) / top) * 100}%`,
                background: r.points < 0 ? "var(--gs-danger)" : r.key === "ai" ? "var(--gs-project)" : r.key === "learned" ? "var(--gs-hiring)" : "var(--gs-signal)" }} />
            </Box>
            <Text size="xs" className="gs-num" w={36} ta="right" c={r.points < 0 ? "var(--gs-danger)" : undefined}>{pts(r.points)}</Text>
          </Group>
        </Tooltip>
      ))}
    </Stack>
  );
}
