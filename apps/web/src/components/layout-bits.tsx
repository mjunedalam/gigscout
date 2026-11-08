import { Sparkline } from "@gigscout/viz";
import { Box, Group, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { type ReactNode, useRef } from "react";

import { AnimatedNumber } from "../lib/motion/AnimatedNumber";
import { MOTION, gsap, prefersReducedMotion, useGSAP } from "../lib/motion/gsap";
import { useReveal } from "../lib/motion/reveal";
import { SplitWords } from "../lib/motion/SplitWords";

interface PageHeaderProps {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

/** Page intro: the eyebrow wipes in, title words rise from behind a mask, then the description and actions settle. */
export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleKey = typeof title === "string" ? title : "";

  useGSAP(
    () => {
      if (prefersReducedMotion()) return;
      gsap
        .timeline({ defaults: { ease: MOTION.ease } })
        .from(".gs-header-eyebrow", { autoAlpha: 0, x: -12, duration: MOTION.fast })
        .from(".gs-word > span", { yPercent: 110, duration: MOTION.slow, stagger: 0.045 }, "<0.05")
        .from(".gs-header-rest", { autoAlpha: 0, y: 10, duration: MOTION.normal, stagger: 0.08 }, "<0.25");
    },
    { scope: ref, dependencies: [titleKey] },
  );

  return (
    <Group ref={ref} justify="space-between" align="flex-end" mb="xl" wrap="wrap" gap="md" className="gs-page-header">
      <Stack gap={6} maw={720}>
        <span className="gs-eyebrow gs-header-eyebrow">
          <span className="gs-eyebrow-tick" aria-hidden />
          {eyebrow}
        </span>
        <Title order={1} className="gs-display gs-page-title">
          {typeof title === "string" ? <SplitWords text={title} /> : title}
        </Title>
        {description && (
          <Text c="var(--gs-text-muted)" size="sm" className="gs-header-rest">
            {description}
          </Text>
        )}
      </Stack>
      {actions && (
        <Group gap="sm" className="gs-header-rest">
          {actions}
        </Group>
      )}
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
  const ref = useRef<HTMLElement>(null);
  useReveal(ref);
  return (
    <Box ref={ref} component="section" className={`gs-panel ${hero ? "gs-panel-hero" : ""} ${className}`} p={padding}>
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
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref);
  return (
    <Box ref={ref} className="gs-panel gs-lift gs-stat" p="lg" style={{ "--stat-accent": accent } as never}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4}>
          <span className="gs-eyebrow">{label}</span>
          <Text className="gs-num" fz={{ base: 30, md: 36 }} fw={500} lh={1.05} style={{ letterSpacing: "-0.03em" }}>
            {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
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
    <Stack align="center" gap="xs" py={48} ta="center" className="gs-empty">
      <div className="gs-empty-icon">
        <ThemeIcon size={52} radius="xl" variant="light">
          {icon}
        </ThemeIcon>
      </div>
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
