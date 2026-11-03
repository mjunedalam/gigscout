import { Sparkline } from "@gigscout/viz";
import { Box, Group, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <Group justify="space-between" align="flex-end" mb="xl" wrap="wrap" gap="md" className="gs-rise">
      <Stack gap={6} maw={720}>
        <span className="gs-eyebrow">{eyebrow}</span>
        <Title order={1} className="gs-display">
          {title}
        </Title>
        {description && (
          <Text c="var(--gs-text-muted)" size="sm">
            {description}
          </Text>
        )}
      </Stack>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}

interface PanelProps {
  title?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  hero?: boolean;
  padding?: number | string;
  className?: string;
}

export function Panel({ title, eyebrow, actions, children, hero, padding = 20, className = "" }: PanelProps) {
  return (
    <Box component="section" className={`gs-panel ${hero ? "gs-panel-hero" : ""} ${className}`} p={padding}>
      {(title || actions || eyebrow) && (
        <Group justify="space-between" mb="md" align="flex-start" wrap="nowrap">
          <Stack gap={2}>
            {eyebrow && <span className="gs-eyebrow">{eyebrow}</span>}
            {title && (
              <Title order={3} className="gs-display">
                {title}
              </Title>
            )}
          </Stack>
          {actions}
        </Group>
      )}
      {children}
    </Box>
  );
}

interface StatTileProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  accent?: string;
  trend?: number[];
}

/** A KPI: a big mono number, a caption, and an optional live sparkline. */
export function StatTile({ label, value, hint, icon, accent = "var(--gs-signal)", trend }: StatTileProps) {
  return (
    <Box className="gs-panel gs-lift" p="lg">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4}>
          <span className="gs-eyebrow">{label}</span>
          <Text className="gs-num" fz={{ base: 30, md: 36 }} fw={500} lh={1.05} style={{ letterSpacing: "-0.03em" }}>
            {value}
          </Text>
          {hint && (
            <Text size="xs" c="var(--gs-text-muted)">
              {hint}
            </Text>
          )}
        </Stack>
        {icon && (
          <ThemeIcon variant="light" size={38} radius="xl" color={accent} style={{ color: accent }}>
            {icon}
          </ThemeIcon>
        )}
      </Group>
      {trend && trend.length > 1 && (
        <Box mt="sm">
          <Sparkline values={trend} width={180} height={30} color={accent} label={`${label} trend`} />
        </Box>
      )}
    </Box>
  );
}

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
}

export function EmptyState({ icon, title, children }: EmptyStateProps) {
  return (
    <Stack align="center" gap="xs" py={48} ta="center">
      <ThemeIcon size={52} radius="xl" variant="light">
        {icon}
      </ThemeIcon>
      <Title order={3} className="gs-display">
        {title}
      </Title>
      {children && (
        <Text size="sm" c="var(--gs-text-muted)" maw={420}>
          {children}
        </Text>
      )}
    </Stack>
  );
}
