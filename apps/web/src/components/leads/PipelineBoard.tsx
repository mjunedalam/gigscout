import { LEAD_STATUSES, type LeadPage, type LeadStatus, type LeadView } from "@gigscout/api-client";
import { STATUS_COLORS } from "@gigscout/viz";
import { Box, Group, Paper, ScrollArea, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type DragEvent, useRef, useState } from "react";

import { api, messageOf } from "../../lib/api";
import { money } from "../../lib/format";
import { KindBadge, ScoreRing } from "../badges";
import { useBoardMotion } from "./useBoardMotion";

interface PipelineBoardProps {
  items: LeadView[];
  onOpen: (id: string) => void;
}

const DRAG_TYPE = "application/x-gigscout-lead";

/** Kanban of the sales pipeline. Drag a card to change its stage; the move is optimistic and rolls back on error. */
export function PipelineBoard({ items, onOpen }: PipelineBoardProps) {
  const queryClient = useQueryClient();
  const [over, setOver] = useState<LeadStatus | null>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const captureMove = useBoardMotion(boardRef, items);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: LeadStatus }) => api.leads.update(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["leads", "list"] });
      const snapshots = queryClient.getQueriesData<LeadPage>({ queryKey: ["leads", "list"] });
      queryClient.setQueriesData<LeadPage>({ queryKey: ["leads", "list"] }, (page) =>
        page && { ...page, items: page.items.map((v) => (v.lead.id === id ? { ...v, status } : v)) },
      );
      return { snapshots };
    },
    onError: (error, _vars, context) => {
      context?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data));
      notifications.show({ color: "red", title: "Move failed, change undone", message: messageOf(error) });
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["metrics"] }),
  });

  const onDrop = (status: LeadStatus) => (event: DragEvent) => {
    event.preventDefault();
    setOver(null);
    const id = event.dataTransfer.getData(DRAG_TYPE);
    const lead = items.find((v) => v.lead.id === id);
    if (!lead || lead.status === status) return;
    captureMove(id);
    move.mutate({ id, status });
  };

  return (
    <div className="gs-board" ref={boardRef}>
      {LEAD_STATUSES.map((status) => {
        const column = items.filter((v) => v.status === status);
        return (
          <Box
            key={status}
            className="gs-column"
            data-over={over === status}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(status);
            }}
            onDragLeave={() => setOver((s) => (s === status ? null : s))}
            onDrop={onDrop(status)}
            aria-label={`${status} column`}
          >
            <Group justify="space-between" mb="sm">
              <Group gap={8}>
                <span className="gs-dot" style={{ background: STATUS_COLORS[status] }} />
                <Text fw={600} tt="capitalize" size="sm">
                  {status}
                </Text>
              </Group>
              <Text size="xs" className="gs-mono" c="var(--gs-text-muted)">
                {column.length}
              </Text>
            </Group>
            <ScrollArea.Autosize mah="62vh" type="hover">
              <Stack gap="xs">
                {column.map((v) => (
                  <Paper
                    key={v.lead.id}
                    data-flip-id={v.lead.id}
                    p="sm"
                    className="gs-panel gs-lift gs-card-drag gs-focus"
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData(DRAG_TYPE, v.lead.id)}
                    onClick={() => onOpen(v.lead.id)}
                    onKeyDown={(e) => e.key === "Enter" && onOpen(v.lead.id)}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open ${v.lead.title}`}
                  >
                    <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                      <Text size="sm" fw={600} lineClamp={2}>
                        {v.lead.title}
                      </Text>
                      <ScoreRing score={v.score} size={36} />
                    </Group>
                    <Group justify="space-between" mt={8}>
                      <KindBadge kind={v.lead.kind} />
                      <Text size="xs" className="gs-num">
                        {money(v.lead)}
                      </Text>
                    </Group>
                    {(v.assignee || v.follow_up_on) && (
                      <Text size="xs" c="var(--gs-text-muted)" mt={6} truncate>
                        {v.assignee ? `👤 ${v.assignee}` : ""}{v.assignee && v.follow_up_on ? " · " : ""}
                        {v.follow_up_on ? `follow up ${v.follow_up_on}` : ""}
                      </Text>
                    )}
                  </Paper>
                ))}
              </Stack>
            </ScrollArea.Autosize>
          </Box>
        );
      })}
    </div>
  );
}
