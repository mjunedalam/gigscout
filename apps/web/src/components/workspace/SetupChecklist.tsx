import type { SetupStep } from "@gigscout/api-client";
import { ActionIcon, Button, Group, Progress, Stack, Text, ThemeIcon, Tooltip, UnstyledButton } from "@mantine/core";
import { IconCheck, IconChevronRight, IconX } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Panel } from "../layout-bits";

const HIDDEN_KEY = "gs-setup-hidden";

function hiddenFor(workspaceId: number): boolean {
  try {
    return (JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]") as number[]).includes(workspaceId);
  } catch {
    return false;
  }
}

function hide(workspaceId: number) {
  try {
    const ids = JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]") as number[];
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...new Set([...ids, workspaceId])]));
  } catch {
    // storage blocked: it simply shows again next time
  }
}

/** First-time setup, worked out from what the workspace has already done; it goes away when done or dismissed. */
export function SetupChecklist() {
  const { workspace, isAdmin } = useAuth();
  const [hidden, setHidden] = useState(() => (workspace ? hiddenFor(workspace.id) : true));
  const steps = useQuery({ queryKey: ["workspace", "setup"], queryFn: api.workspaces.setup, enabled: !!workspace && !hidden });
  const list = steps.data ?? [];
  const done = list.filter((s) => s.done).length;
  if (!workspace || hidden || !list.length || done === list.length) return null;
  const next = list.find((s) => !s.done && (isAdmin || !s.admin_only));

  return (
    <Panel eyebrow={`Getting started · ${done} of ${list.length}`} title={`Set up ${workspace.name}`} className="gs-rise"
      actions={
        <Tooltip label="Hide the checklist">
          <ActionIcon variant="subtle" color="gray" aria-label="Hide the checklist" onClick={() => { hide(workspace.id); setHidden(true); }}>
            <IconX size={16} />
          </ActionIcon>
        </Tooltip>
      }>
      <Progress value={(done / list.length) * 100} size="sm" radius="xl" color="signal" mb="md" aria-label={`${done} of ${list.length} steps done`} />
      <Stack gap={4}>
        {list.map((s) => <Step key={s.id} step={s} canDo={isAdmin || !s.admin_only} isNext={s.id === next?.id} />)}
      </Stack>
    </Panel>
  );
}

function Step({ step, canDo, isNext }: { step: SetupStep; canDo: boolean; isNext: boolean }) {
  const body = (
    <Group wrap="nowrap" gap="md" py={8} px={10} style={{ borderRadius: 10, background: isNext ? "var(--gs-btn-soft)" : undefined }}>
      <ThemeIcon radius="xl" size={26} variant={step.done ? "filled" : "light"} color={step.done ? "signal" : "gray"}>
        {step.done ? <IconCheck size={14} /> : <span style={{ width: 8, height: 8, borderRadius: 8, background: "currentColor" }} />}
      </ThemeIcon>
      <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
        <Text size="sm" fw={600} td={step.done ? "line-through" : undefined} c={step.done ? "var(--gs-text-muted)" : undefined}>{step.label}</Text>
        {!step.done && <Text size="xs" c="var(--gs-text-muted)">{canDo ? step.help : "An owner or admin does this step."}</Text>}
      </Stack>
      {!step.done && canDo && (isNext
        ? <Button size="xs" component="span" rightSection={<IconChevronRight size={14} />}>Start</Button>
        : <IconChevronRight size={16} color="var(--gs-text-muted)" />)}
    </Group>
  );
  return !step.done && canDo ? <UnstyledButton component={Link} to={step.href} className="gs-focus" style={{ display: "block" }}>{body}</UnstyledButton> : body;
}
