import { Box, Group, SimpleGrid, Skeleton, Stack } from "@mantine/core";
import type { ReactNode } from "react";

/**
 * Loading placeholders shaped like the screen they stand in for, so the layout does not jump when data lands.
 * Every one is hidden from assistive tech and announced once through the wrapping status region.
 */

interface SkeletonFrameProps {
  label: string;
  children: ReactNode;
}

function SkeletonFrame({ label, children }: SkeletonFrameProps) {
  return (
    <Box role="status" aria-live="polite" aria-busy="true" className="gs-skeleton">
      <span className="gs-sr-only">{label}</span>
      <div aria-hidden="true">{children}</div>
    </Box>
  );
}

// Varied widths read as real text; identical bars read as a loading bar.
const LINE_WIDTHS = ["72%", "54%", "86%", "63%", "78%", "47%", "69%", "58%"];

interface TableSkeletonProps {
  rows?: number;
  label?: string;
}

export function TableSkeleton({ rows = 8, label = "Loading leads" }: TableSkeletonProps) {
  return (
    <SkeletonFrame label={label}>
      <Box className="gs-panel" p="md">
        <Group gap="md" mb="md" wrap="nowrap">
          <Skeleton h={10} w="30%" />
          <Skeleton h={10} w="12%" ml="auto" />
          <Skeleton h={10} w="10%" />
        </Group>
        <Stack gap={14}>
          {Array.from({ length: rows }, (_, i) => (
            <Group key={i} gap="md" wrap="nowrap">
              <Skeleton circle h={30} w={30} />
              <Stack gap={6} style={{ flex: 1 }}>
                <Skeleton h={12} w={LINE_WIDTHS[i % LINE_WIDTHS.length]} />
                <Skeleton h={8} w="28%" />
              </Stack>
              <Skeleton h={20} w={84} radius="sm" visibleFrom="sm" />
              <Skeleton h={12} w={64} />
            </Group>
          ))}
        </Stack>
      </Box>
    </SkeletonFrame>
  );
}

interface ListSkeletonProps {
  rows?: number;
  label?: string;
}

export function ListSkeleton({ rows = 4, label = "Loading" }: ListSkeletonProps) {
  return (
    <SkeletonFrame label={label}>
      <Stack gap="sm">
        {Array.from({ length: rows }, (_, i) => (
          <Box key={i} className="gs-panel" p="md">
            <Skeleton h={12} w={LINE_WIDTHS[i % LINE_WIDTHS.length]} mb={10} />
            <Skeleton h={8} w="92%" mb={6} />
            <Skeleton h={8} w="64%" />
          </Box>
        ))}
      </Stack>
    </SkeletonFrame>
  );
}

const BOARD_COLUMNS = 6;
const CARDS_PER_COLUMN = [3, 2, 4, 1, 2, 1];

export function BoardSkeleton() {
  return (
    <SkeletonFrame label="Loading pipeline">
      <div className="gs-board">
        {Array.from({ length: BOARD_COLUMNS }, (_, c) => (
          <Box key={c} className="gs-column">
            <Group justify="space-between" mb="sm">
              <Skeleton h={10} w="40%" />
              <Skeleton h={10} w={16} />
            </Group>
            <Stack gap="xs">
              {Array.from({ length: CARDS_PER_COLUMN[c] ?? 1 }, (_, i) => (
                <Box key={i} className="gs-panel" p="sm">
                  <Group justify="space-between" wrap="nowrap" align="flex-start">
                    <Stack gap={6} style={{ flex: 1 }}>
                      <Skeleton h={10} w="90%" />
                      <Skeleton h={10} w="60%" />
                    </Stack>
                    <Skeleton circle h={36} w={36} />
                  </Group>
                  <Group justify="space-between" mt={10}>
                    <Skeleton h={16} w={70} radius="sm" />
                    <Skeleton h={10} w={44} />
                  </Group>
                </Box>
              ))}
            </Stack>
          </Box>
        ))}
      </div>
    </SkeletonFrame>
  );
}

interface ChartPanelSkeletonProps {
  height: number;
}

function ChartPanelSkeleton({ height }: ChartPanelSkeletonProps) {
  return (
    <Box className="gs-panel" p="lg">
      <Skeleton h={8} w={90} mb={10} />
      <Skeleton h={14} w="45%" mb="lg" />
      <Skeleton h={height} radius="md" />
    </Box>
  );
}

export function ChartsSkeleton() {
  return (
    <SkeletonFrame label="Loading analytics">
      <Stack gap="md">
        <ChartPanelSkeleton height={200} />
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          <ChartPanelSkeleton height={240} />
          <ChartPanelSkeleton height={240} />
        </SimpleGrid>
      </Stack>
    </SkeletonFrame>
  );
}

/** The fallback while a screen's code chunk loads: header, a row of stats, one panel. */
export function PageSkeleton() {
  return (
    <SkeletonFrame label="Loading screen">
      <Box mb="xl">
        <Skeleton h={8} w={80} mb={14} />
        <Skeleton h={30} w="min(420px, 70%)" mb={12} />
        <Skeleton h={10} w="min(560px, 90%)" />
      </Box>
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md" mb="md">
        {Array.from({ length: 4 }, (_, i) => (
          <Box key={i} className="gs-panel" p="lg">
            <Skeleton h={8} w="50%" mb={14} />
            <Skeleton h={26} w="40%" />
          </Box>
        ))}
      </SimpleGrid>
      <ChartPanelSkeleton height={220} />
    </SkeletonFrame>
  );
}

/** Before we know who is signed in: just the shell's silhouette, no spinner. */
export function ShellSkeleton() {
  return (
    <SkeletonFrame label="Signing you in">
      <Box p="lg" maw={1200} mx="auto">
        <Group justify="space-between" mb={40}>
          <Skeleton h={28} w={140} radius="xl" />
          <Skeleton circle h={34} w={34} />
        </Group>
        <PageSkeletonBody />
      </Box>
    </SkeletonFrame>
  );
}

function PageSkeletonBody() {
  return (
    <>
      <Skeleton h={30} w="min(420px, 70%)" mb={12} />
      <Skeleton h={10} w="min(560px, 90%)" mb="xl" />
      <ChartPanelSkeleton height={260} />
    </>
  );
}
