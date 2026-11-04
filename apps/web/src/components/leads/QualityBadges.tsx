import type { Lead } from "@gigscout/api-client";
import { Badge, Group, Tooltip } from "@mantine/core";
import { IconCopy, IconShieldX, IconAlertTriangle } from "@tabler/icons-react";

/** What the automated quality check found: likely scams in red, lesser concerns in orange, repeats in grey. */
export function QualityBadges({ lead, compact = false }: { lead: Lead; compact?: boolean }) {
  const flags = lead.quality ?? [];
  if (!flags.length && !lead.duplicate_of) return null;
  const scams = flags.filter((f) => f.severity === "scam");
  const warnings = flags.filter((f) => f.severity === "warning");
  if (compact) {
    const text = [...flags.map((f) => f.label), ...(lead.duplicate_of ? ["duplicate of an earlier lead"] : [])].join(" · ");
    return (
      <Tooltip label={text} multiline w={260}>
        <span aria-label={`Quality: ${text}`} style={{ display: "inline-flex" }}>
          {scams.length ? <IconShieldX size={14} color="var(--gs-danger)" />
            : lead.duplicate_of ? <IconCopy size={14} color="var(--gs-text-muted)" />
              : <IconAlertTriangle size={14} color="var(--mantine-color-orange-5)" />}
        </span>
      </Tooltip>
    );
  }
  return (
    <Group gap={6}>
      {scams.map((f) => <Badge key={f.label} size="sm" color="red" variant="light" leftSection={<IconShieldX size={12} />} tt="none">Likely scam: {f.label}</Badge>)}
      {warnings.map((f) => <Badge key={f.label} size="sm" color="orange" variant="light" leftSection={<IconAlertTriangle size={12} />} tt="none">{f.label}</Badge>)}
      {lead.duplicate_of && <Badge size="sm" color="gray" variant="light" leftSection={<IconCopy size={12} />} tt="none">Duplicate of an earlier lead</Badge>}
    </Group>
  );
}
