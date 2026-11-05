import type { Outreach } from "@gigscout/api-client";
import { Badge, Button, Group, Stack, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBriefcase, IconDatabaseExport, IconMail, IconSparkles, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, messageOf } from "../../lib/api";
import { timeAgo } from "../../lib/format";
import { PitchEditor } from "../pitches/PitchEditor";
import { LogReplyButton } from "../replies/LogReplyButton";

const STATUS_COLOR: Record<Outreach["status"], string> = {
  draft: "gray", rejected: "red", sent: "blue", replied: "signal", no_reply: "orange",
};
const STATUS_LABEL: Record<Outreach["status"], string> = {
  draft: "waiting for approval", rejected: "rejected", sent: "sent", replied: "replied", no_reply: "no reply",
};
const CRM_LABEL: Record<string, string> = { hubspot: "HubSpot", pipedrive: "Pipedrive" };

/** Draft a message for the lead, approve or reject it (email or marketplace bid), track replies, push to the CRM. */
export function LeadOutreach({ leadId, leadUrl }: { leadId: string; leadUrl?: string }) {
  const queryClient = useQueryClient();
  const key = ["outreach", leadId];
  const config = useQuery({ queryKey: ["outreach", "config"], queryFn: api.outreach.config, staleTime: 60_000 });
  const history = useQuery({ queryKey: key, queryFn: () => api.outreach.list(leadId) });
  const pitches = useQuery({ queryKey: ["pitches", "summary"], queryFn: api.pitches.summary });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: ["pitches"] });
    void queryClient.invalidateQueries({ queryKey: ["leads"] }); // sending moves a new lead to "contacted"
    void queryClient.invalidateQueries({ queryKey: ["replies"] });
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
        <PitchEditor key={open.id} draft={open} emailReady={config.data?.email_ready ?? false} leadUrl={leadUrl}
          canApprove={pitches.data?.can_approve ?? false} onDone={refresh} />
      ) : (
        <Button variant="light" leftSection={<IconSparkles size={16} />} loading={draft.isPending} onClick={() => draft.mutate()}>
          {draft.isPending ? "Writing a first message…" : sent.length ? "Draft a follow-up" : "Draft a first message"}
        </Button>
      )}
      {sent.map((m) => (
        <Group key={m.id} justify="space-between" wrap="nowrap" gap="xs">
          <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
            {m.status === "rejected" ? <IconX size={14} /> : m.channel === "email" ? <IconMail size={14} /> : <IconBriefcase size={14} />}
            <Tooltip label={m.review_note || "No reason given"} disabled={m.status !== "rejected"} multiline w={260}>
              <Text size="xs" truncate>
                {m.status === "rejected"
                  ? `Rejected by ${m.reviewed_by ?? "someone"} · ${m.reviewed_at ? timeAgo(m.reviewed_at) : ""}`
                  : `${m.channel === "email" ? `Emailed ${m.to}` : "Bid posted"} · ${m.sent_at ? timeAgo(m.sent_at) : ""} · approved by ${m.reviewed_by ?? m.created_by}`}
              </Text>
            </Tooltip>
          </Group>
          <Group gap={4} wrap="nowrap">
            <Badge size="sm" variant="light" color={STATUS_COLOR[m.status]}>{STATUS_LABEL[m.status]}</Badge>
            {m.status === "sent" && (
              <>
                <LogReplyButton outreachId={m.id} isEmail={m.channel === "email"} onDone={refresh} />
                <Button size="compact-xs" variant="subtle" color="gray" onClick={() => reply.mutate({ id: m.id, status: "no_reply" })}>No reply</Button>
              </>
            )}
          </Group>
        </Group>
      ))}
    </Stack>
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
