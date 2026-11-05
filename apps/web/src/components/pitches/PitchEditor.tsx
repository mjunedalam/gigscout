import type { Outreach, OutreachInput } from "@gigscout/api-client";
import {
  Badge, Button, CopyButton, Group, Paper, Popover, SegmentedControl, Stack, Text, Textarea, TextInput, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconCopy, IconExternalLink, IconRobot, IconSend, IconSparkles, IconX } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, messageOf } from "../../lib/api";
import { Grounding } from "./Grounding";

export const AGENT_AUTHOR = "GigScout agents";
const SMTP_HINT = "Set GIGSCOUT_SMTP_HOST and GIGSCOUT_SMTP_FROM in apps/api/.env";
const APPROVER_HINT = "An owner or admin must approve messages in this workspace";

interface PitchEditorProps {
  draft: Outreach;
  emailReady: boolean;
  canApprove: boolean;
  /** The listing, so a bid can be pasted into it. */
  leadUrl?: string;
  onDone: () => void;
}

const inputOf = (d: Outreach): OutreachInput => ({ channel: d.channel, to: d.to, subject: d.subject, body: d.body });

/** A drafted message waiting for a person: edit it, then approve (send it, or post the bid) or reject it. */
export function PitchEditor({ draft, emailReady, canApprove, leadUrl, onDone }: PitchEditorProps) {
  const [value, setValue] = useState<OutreachInput>(inputOf(draft));
  useEffect(() => setValue(inputOf(draft)), [draft]);
  const set = (change: Partial<OutreachInput>) => setValue((v) => ({ ...v, ...change }));
  const isEmail = value.channel === "email";
  const failed = (title: string) => (e: unknown) =>
    notifications.show({ color: "red", autoClose: 10000, title, message: messageOf(e) });

  const save = useMutation({ mutationFn: () => api.outreach.edit(draft.id, value), onSuccess: onDone, onError: failed("Could not save") });
  const approve = useMutation({
    mutationFn: () => api.outreach.send(draft.id, value), // what is on screen is exactly what goes out
    onSuccess: (m) => {
      notifications.show({ color: "signal", title: m.channel === "email" ? `Email sent to ${m.to}` : "Approved and marked as posted", message: "The lead moved to contacted." });
      onDone();
    },
    onError: failed("Not sent"),
  });

  return (
    <Paper p="sm" radius="md" withBorder>
      <Stack gap="xs">
        <Group justify="space-between" wrap="wrap" gap="xs">
          <SegmentedControl size="xs" value={value.channel} onChange={(c) => set({ channel: c as OutreachInput["channel"] })}
            data={[{ value: "email", label: "Email" }, { value: "bid", label: "Marketplace bid" }]} />
          <Group gap={4}>
            {draft.kind === "follow_up" && <Badge size="sm" variant="light" color="orange">follow-up</Badge>}
            {draft.kind === "answer" && <Badge size="sm" variant="light" color="teal">answer to a reply</Badge>}
            {draft.created_by === AGENT_AUTHOR && (
              <Badge size="sm" variant="light" color="violet" leftSection={<IconRobot size={10} />}>by the agents</Badge>
            )}
            <Badge size="sm" variant="light" color={draft.source === "ai" ? "signal" : "gray"}
              leftSection={draft.source === "ai" ? <IconSparkles size={10} /> : undefined}>
              {draft.source === "ai" ? "AI draft" : "template"}
            </Badge>
          </Group>
        </Group>
        {isEmail && (
          <>
            <TextInput size="xs" label="To" placeholder="name@client.com" value={value.to ?? ""} maxLength={254}
              onChange={(e) => set({ to: e.currentTarget.value.trim() || null })} />
            <TextInput size="xs" label="Subject" value={value.subject} maxLength={200}
              onChange={(e) => set({ subject: e.currentTarget.value.replace(/[\r\n]/g, " ") })} />
          </>
        )}
        <Textarea size="xs" label={isEmail ? "Message" : "Proposal text"} autosize minRows={6} maxRows={16} maxLength={5000}
          value={value.body} onChange={(e) => set({ body: e.currentTarget.value })} />
        <Grounding evidence={draft.evidence} claims={draft.claims} body={value.body} />
        <Group justify="space-between" gap="xs" wrap="wrap">
          <RejectButton draftId={draft.id} disabled={!canApprove} onDone={onDone} />
          <Group gap="xs" wrap="wrap">
            <Button size="xs" variant="subtle" loading={save.isPending} onClick={() => save.mutate()}>Save draft</Button>
            {isEmail ? (
              <Tooltip label={!canApprove ? APPROVER_HINT : SMTP_HINT} disabled={canApprove && emailReady}>
                <Button size="xs" leftSection={<IconSend size={14} />} loading={approve.isPending}
                  disabled={!canApprove || !emailReady || !value.to || !value.subject} onClick={() => approve.mutate()}>
                  Approve &amp; send
                </Button>
              </Tooltip>
            ) : (
              <>
                <CopyButton value={value.body}>
                  {({ copied, copy }) => (
                    <Button size="xs" variant="light" leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />} onClick={copy}>
                      {copied ? "Copied" : "Copy"}
                    </Button>
                  )}
                </CopyButton>
                {leadUrl && (
                  <Button size="xs" variant="light" component="a" href={leadUrl} target="_blank" rel="noopener noreferrer"
                    leftSection={<IconExternalLink size={14} />}>Open listing</Button>
                )}
                <Tooltip label={APPROVER_HINT} disabled={canApprove}>
                  <Button size="xs" leftSection={<IconCheck size={14} />} loading={approve.isPending} disabled={!canApprove}
                    onClick={() => approve.mutate()}>Approve as posted</Button>
                </Tooltip>
              </>
            )}
          </Group>
        </Group>
      </Stack>
    </Paper>
  );
}

function RejectButton({ draftId, disabled, onDone }: { draftId: number; disabled: boolean; onDone: () => void }) {
  const [opened, setOpened] = useState(false);
  const [note, setNote] = useState("");
  const reject = useMutation({
    mutationFn: () => api.outreach.reject(draftId, note),
    onSuccess: () => {
      setOpened(false);
      notifications.show({ color: "gray", message: "Pitch rejected. It stays in the Rejected tab with your reason." });
      onDone();
    },
    onError: (e) => notifications.show({ color: "red", title: "Could not reject", message: messageOf(e) }),
  });
  return (
    <Popover opened={opened} onChange={setOpened} position="top-start" width={300} withArrow trapFocus>
      <Popover.Target>
        <Button size="xs" variant="subtle" color="red" leftSection={<IconX size={14} />} disabled={disabled}
          onClick={() => setOpened((o) => !o)}>Reject</Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs">
          <Text size="xs">Why not? The team sees this in the Rejected tab.</Text>
          <Textarea size="xs" autosize minRows={2} maxLength={500} placeholder="Too generic, wrong client, already talking to them…"
            value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button size="xs" color="red" loading={reject.isPending} onClick={() => reject.mutate()}>Reject pitch</Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
