import type { LiveEvent } from "@gigscout/api-client";
import { Group, ScrollArea, Stack, Text, ThemeIcon } from "@mantine/core";

import { timeAgo } from "../lib/format";
import { describeEvent } from "./describe-event";

interface ActivityFeedProps {
  events: LiveEvent[];
  height?: number;
}

export function ActivityFeed({ events, height = 360 }: ActivityFeedProps) {
  if (!events.length) {
    return (
      <Text size="sm" c="var(--gs-text-muted)" py="lg">
        Quiet for now. Runs, inbound enquiries and pipeline moves will stream in here live.
      </Text>
    );
  }
  return (
    <ScrollArea h={height} type="auto" offsetScrollbars>
      <Stack gap={4}>
        {events.map((event) => {
          const { icon, color, text } = describeEvent(event);
          return (
            <Group key={event.id} gap="sm" wrap="nowrap" py={6} className="gs-rise" align="flex-start">
              <ThemeIcon size={26} radius="xl" variant="light" color={color}>
                {icon}
              </ThemeIcon>
              <Stack gap={0} style={{ minWidth: 0 }}>
                <Text size="sm" lineClamp={2}>
                  {text}
                </Text>
                <Text size="xs" c="var(--gs-text-muted)" className="gs-mono">
                  {timeAgo(event.at)}
                </Text>
              </Stack>
            </Group>
          );
        })}
      </Stack>
    </ScrollArea>
  );
}
