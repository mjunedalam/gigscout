import type { LeadKind, LeadStatus, RunStatus } from "@gigscout/api-client";
import { KIND_COLORS, KIND_LABELS, scoreColor } from "@gigscout/viz";
import { Badge, RingProgress, Text, Tooltip } from "@mantine/core";

export function KindBadge({ kind }: { kind: LeadKind }) {
  return (
    <Badge
      variant="dot"
      tt="none"
      styles={{ root: { "--badge-dot-color": KIND_COLORS[kind], borderColor: "var(--gs-line)" } as never, label: { letterSpacing: 0, overflow: "visible" } }}
    >
      {KIND_LABELS[kind]}
    </Badge>
  );
}

/* Badges use theme colour names (readable in both themes); the viz hex colours stay for charts. */
const LEAD_STATUS_BADGE: Record<LeadStatus, string> = {
  new: "gray", contacted: "blue", proposal: "violet", won: "signal", lost: "red", archived: "gray",
};
const RUN_STATUS_BADGE: Record<RunStatus, string> = {
  queued: "gray", running: "blue", succeeded: "signal", failed: "red", cancelled: "gray",
};

export function StatusBadge({ status }: { status: LeadStatus }) {
  return (
    <Badge color={LEAD_STATUS_BADGE[status]} variant="light" tt="capitalize">
      {status}
    </Badge>
  );
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge
      color={RUN_STATUS_BADGE[status]}
      variant={status === "running" ? "filled" : "light"}
      leftSection={status === "running" ? <span className="gs-live-dot" style={{ width: 6, height: 6 }} /> : null}
    >
      {status}
    </Badge>
  );
}

interface ScoreRingProps {
  score: number | null;
  size?: number;
}

/** A lead's qualification score as a ring; unscored leads show an empty ring. */
export function ScoreRing({ score, size = 44 }: ScoreRingProps) {
  const value = score === null ? 0 : Math.round(score * 100);
  return (
    <Tooltip label={score === null ? "Not qualified yet" : `Score ${score.toFixed(2)}`}>
      <RingProgress
        size={size}
        thickness={size / 11}
        roundCaps
        sections={[{ value, color: scoreColor(score) }]}
        rootColor="var(--gs-line)"
        label={
          <Text ta="center" size={size > 50 ? "sm" : "xs"} fw={600} className="gs-num">
            {score === null ? "–" : value}
          </Text>
        }
      />
    </Tooltip>
  );
}
