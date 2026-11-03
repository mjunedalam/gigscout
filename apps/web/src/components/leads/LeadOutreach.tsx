import type { Outreach, OutreachInput } from "@gigscout/api-client";
import {
  Badge, Button, CopyButton, Group, Paper, SegmentedControl, Stack, Text, Textarea, TextInput, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBriefcase, IconCopy, IconDatabaseExport, IconMail, IconSend, IconSparkles } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, messageOf } from "../../lib/api";
import { timeAgo } from "../../lib/format";

const STATUS_COLOR: Record<Outreach["status"], string> = { draft: "gray", sent: "blue", replied: "signal", no_reply: "orange" };
const STATUS_LABEL: Record<Outreach["status"], string> = { draft: "draft", sent: "sent", replied: "replied", no_reply: "no reply" };
const CRM_LABEL: Record<string, string> = { hubspot: "HubSpot", pipedrive: "Pipedrive" };

/** Draft a first message for the lead, edit it, send it (email or marketplace bid), track replies, push to the CRM. */
export function LeadOutreach({ leadId }: { leadId: string }) {
  const queryClient = useQueryClient();
  const key = ["outreach", leadId];
  const config = useQuery({ queryKey: ["outreach", "config"], queryFn: api.outreach.config, staleTime: 60_000 });
  const history = useQuery({ queryKey: key, queryFn: () => api.outreach.list(leadId) });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: ["leads"] }); // sending moves a new lead to "contacted"
  };
  const failed = (title: string) => (e: unknown) => notifications.show({ color: "red", title, message: messageOf(e) });

  const draft = useMutation({ mutationFn: () => api.outreach.draft(leadId), onSuccess: refresh, onError: failed("Could not draft") });
  const reply = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "replied" | "no_reply" }) => api.outreach.setStatus(id, status),
    onSuccess: refresh, onError: failed("Could not update"),
  });

  const messages = history.data ?? [];
  const open = messages.find((m) => m.status === "draft");
  const sent = messages.filter((m) => m.status !== "draft");

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <span className="gs-eyebrow">Outreach</span>
        <CrmButton leadId={leadId} crms={config.data?.crms ?? []} />
      </Group>
      {open ? (
        <DraftEditor key={open.id} draft={open} emailReady={config.data?.email_ready ?? false} onDone={refresh} />
      ) : (
        <Button variant="light" leftSection={<IconSparkles size={16} />} loading={draft.isPending} onClick={() => draft.mutate()}>
          {draft.isPending ? "Writing a first message…" : sent.length ? "Draft a follow-up" : "Draft a first message"}
        </Button>
      )}
      {sent.map((m) => (
        <Group key={m.id} justify="space-between" wrap="nowrap" gap="xs">
          <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
            {m.channel === "email" ? <IconMail size={14} /> : <IconBriefcase size={14} />}
            <Text size="xs" truncate>
              {m.channel === "email" ? `Emailed ${m.to}` : "Bid posted"} · {m.sent_at ? timeAgo(m.sent_at) : ""} · {m.created_by}
            </Text>
          </Group>
          <Group gap={4} wrap="nowrap">
            <Badge size="sm" variant="light" color={STATUS_COLOR[m.status]}>{STATUS_LABEL[m.status]}</Badge>
            {m.status === "sent" && (
              <>
                <Button size="compact-xs" variant="subtle" onClick={() => reply.mutate({ id: m.id, status: "replied" })}>Got a reply</Button>
                <Button size="compact-xs" variant="subtle" color="gray" onClick={() => reply.mutate({ id: m.id, status: "no_reply" })}>No reply</Button>
              </>
            )}
          </Group>
        </Group>
      ))}
    </Stack>
  );
}

function DraftEditor({ draft, emailReady, onDone }: { draft: Outreach; emailReady: boolean; onDone: () => void }) {
  const [value, setValue] = useState<OutreachInput>({ channel: draft.channel, to: draft.to, subject: draft.subject, body: draft.body });
  useEffect(() => setValue({ channel: draft.channel, to: draft.to, subject: draft.subject, body: draft.body }), [draft]);
  const set = (change: Partial<OutreachInput>) => setValue((v) => ({ ...v, ...change }));
  const isEmail = value.channel === "email";

  const save = useMutation({ mutationFn: () => api.outreach.edit(draft.id, value), onSuccess: onDone,
    onError: (e) => notifications.show({ color: "red", title: "Could not save", message: messageOf(e) }) });
  const send = useMutation({
    mutationFn: async () => {
      await api.outreach.edit(draft.id, value);
      return api.outreach.send(draft.id);
    },
    onSuccess: (m) => {
      notifications.show({ color: "signal", title: m.channel === "email" ? `Email sent to ${m.to}` : "Marked as posted", message: "The lead moved to contacted." });
      onDone();
    },
    onError: (e) => notifications.show({ color: "red", autoClose: 10000, title: "Not sent", message: messageOf(e) }),
  });

  return (
    <Paper p="sm" radius="md" withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <SegmentedControl size="xs" value={value.channel} onChange={(c) => set({ channel: c as OutreachInput["channel"] })}
            data={[{ value: "email", label: "Email" }, { value: "bid", label: "Marketplace bid" }]} />
          <Badge size="sm" variant="light" color={draft.source === "ai" ? "signal" : "gray"}
            leftSection={draft.source === "ai" ? <IconSparkles size={10} /> : undefined}>
            {draft.source === "ai" ? "AI draft" : "template"}
          </Badge>
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
        <Group justify="flex-end" gap="xs">
          <Button size="xs" variant="subtle" loading={save.isPending} onClick={() => save.mutate()}>Save draft</Button>
          {isEmail ? (
            <Tooltip label="Set GIGSCOUT_SMTP_HOST and GIGSCOUT_SMTP_FROM in apps/api/.env" disabled={emailReady}>
              <Button size="xs" leftSection={<IconSend size={14} />} disabled={!emailReady || !value.to || !value.subject}
                loading={send.isPending} onClick={() => send.mutate()}>Send email</Button>
            </Tooltip>
          ) : (
            <>
              <CopyButton value={value.body}>
                {({ copied, copy }) => (
                  <Button size="xs" variant="light" leftSection={<IconCopy size={14} />} onClick={copy}>{copied ? "Copied" : "Copy"}</Button>
                )}
              </CopyButton>
              <Button size="xs" loading={send.isPending} onClick={() => send.mutate()}>Mark as posted</Button>
            </>
          )}
        </Group>
      </Stack>
    </Paper>
  );
}

function CrmButton({ leadId, crms }: { leadId: string; crms: string[] }) {
  const queryClient = useQueryClient();
  const key = ["outreach", "crm", leadId];
  const links = useQuery({ queryKey: key, queryFn: () => api.outreach.crmLinks(leadId), enabled: crms.length > 0 });
  const push = useMutation({
    mutationFn: () => api.outreach.pushToCrm(leadId),
    onSuccess: (r) => {
      queryClient.setQueryData(key, r);
      notifications.show(r.errors.length
        ? { color: "orange", title: "Partly pushed", message: r.errors.join("; ") }
        : { color: "signal", message: `Deal created in ${r.links.map((l) => CRM_LABEL[l.crm] ?? l.crm).join(" and ")}` });
    },
    onError: (e) => notifications.show({ color: "red", title: "Not pushed to the CRM", message: messageOf(e) }),
  });

  if (!crms.length) {
    return (
      <Tooltip label="Set GIGSCOUT_HUBSPOT_TOKEN or GIGSCOUT_PIPEDRIVE_TOKEN in apps/api/.env" multiline w={240}>
        <Text size="xs" c="var(--gs-text-muted)">No CRM connected</Text>
      </Tooltip>
    );
  }
  const done = links.data?.links ?? [];
  const missing = crms.filter((c) => !done.some((l) => l.crm === c));
  if (!missing.length) {
    return <Badge variant="light" color="signal">In {done.map((l) => CRM_LABEL[l.crm] ?? l.crm).join(" & ")}</Badge>;
  }
  return (
    <Button size="compact-xs" variant="light" leftSection={<IconDatabaseExport size={12} />} loading={push.isPending}
      onClick={() => push.mutate()}>
      Send to {missing.map((c) => CRM_LABEL[c] ?? c).join(" & ")}
    </Button>
  );
}
