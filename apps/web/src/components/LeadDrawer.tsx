import { LEAD_STATUSES, type LeadChange, type LeadStatus } from "@gigscout/api-client";
import {
  Alert,
  Anchor,
  Badge,
  Button,
  CopyButton,
  Divider,
  Drawer,
  Group,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  Textarea,
  Title,
  Select,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconCheck, IconCopy, IconExternalLink, IconMessage2Bolt, IconSchool } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { clientLabel, dateTime, money } from "../lib/format";
import { KindBadge, ScoreRing } from "./badges";
import { LeadOutreach } from "./leads/LeadOutreach";
import { QualityBadges } from "./leads/QualityBadges";
import { ScoreBreakdown } from "./leads/ScoreBreakdown";

interface LeadDrawerProps {
  leadId: string | null;
  onClose: () => void;
}

/** Everything about one lead, plus the actions a salesperson takes on it: move stage, take notes, copy the pitch. */
export function LeadDrawer({ leadId, onClose }: LeadDrawerProps) {
  const queryClient = useQueryClient();
  const lead = useQuery({ queryKey: ["leads", "one", leadId], queryFn: () => api.leads.get(leadId!), enabled: !!leadId });
  const [notes, setNotes] = useState("");
  useEffect(() => {
    setNotes(lead.data?.notes ?? "");
  }, [lead.data?.notes]);

  const { canWrite } = useAuth();
  const members = useQuery({ queryKey: ["workspace", "members"], queryFn: api.workspaces.members, staleTime: 60_000 });
  const update = useMutation({
    mutationFn: (change: LeadChange) => api.leads.update(leadId!, change),
    onSuccess: (view) => {
      queryClient.setQueryData(["leads", "one", leadId], view);
      void queryClient.invalidateQueries({ queryKey: ["leads"] });
      void queryClient.invalidateQueries({ queryKey: ["metrics"] });
      notifications.show({ color: "signal", message: "Lead updated", icon: <IconCheck size={16} /> });
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not update lead", message: messageOf(error) }),
  });

  const view = lead.data;
  return (
    <Drawer opened={!!leadId} onClose={onClose} position="right" size="lg" title={<span className="gs-eyebrow">Lead</span>}>
      {lead.isPending && <Skeleton h={320} radius="lg" />}
      {lead.isError && <Alert color="red">{messageOf(lead.error)}</Alert>}
      {view && (
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Stack gap={8}>
              <Group gap={6}>
                <KindBadge kind={view.lead.kind} />
                <Badge variant="outline" color="gray">
                  {view.lead.source}
                </Badge>
              </Group>
              <Title order={2} className="gs-display">
                {view.lead.title}
              </Title>
              <Text size="sm" c="var(--gs-text-muted)">
                {clientLabel(view.lead)} · posted {dateTime(view.lead.posted_at)}
              </Text>
            </Stack>
            <ScoreRing score={view.score} size={68} />
          </Group>

          <Group gap="xl">
            <Fact label="Budget" value={money(view.lead)} />
            <Fact label="Competing bids" value={view.lead.bid_count ?? "—"} />
            {view.lead.client?.email && <Fact label="Email" value={view.lead.client.email} />}
            {view.lead.client?.phone && <Fact label="Phone" value={view.lead.client.phone} />}
          </Group>

          <Stack gap={6}>
            <span className="gs-eyebrow">Pipeline stage</span>
            <SegmentedControl
              fullWidth
              size="xs"
              value={view.status}
              data={LEAD_STATUSES.map((s) => ({ value: s, label: s }))}
              onChange={(status) => update.mutate({ status: status as LeadStatus })}
              disabled={update.isPending || !canWrite}
            />
          </Stack>

          <Group grow align="flex-end">
            <Select label="Owner" placeholder="Nobody yet" clearable data={(members.data ?? []).map((m, _, all) => ({
                value: String(m.id),
                label: all.filter((o) => o.name === m.name).length > 1 ? `${m.name} (${m.hint})` : m.name,
              }))}
              value={view.assigned_to ? String(view.assigned_to) : null} disabled={update.isPending || !canWrite}
              onChange={(v) => update.mutate({ assigned_to: v ? Number(v) : null })} />
            <TextInput label="Follow up on" type="date" value={view.follow_up_on ?? ""} disabled={update.isPending || !canWrite}
              onChange={(e) => update.mutate({ follow_up_on: e.currentTarget.value || null })} />
          </Group>

          {view.pitch && (
            <Alert variant="light" color="signal" icon={<IconMessage2Bolt size={18} />} title="Suggested opener">
              <Text size="sm">{view.pitch}</Text>
              <CopyButton value={view.pitch}>
                {({ copied, copy }) => (
                  <Button size="compact-xs" variant="subtle" mt={6} leftSection={<IconCopy size={12} />} onClick={copy}>
                    {copied ? "Copied" : "Copy pitch"}
                  </Button>
                )}
              </CopyButton>
            </Alert>
          )}
          {view.reasons && (
            <Text size="sm">
              <b>Why it fits: </b>
              {view.reasons}
            </Text>
          )}
          {view.learned !== 0 && view.learned_note && (
            <Group gap={6} wrap="nowrap">
              <Badge size="sm" variant="light" color={view.learned > 0 ? "signal" : "orange"} leftSection={<IconSchool size={12} />}>
                {view.learned > 0 ? "+" : ""}{Math.round(view.learned * 100)} learned
              </Badge>
              <Text size="xs" c="var(--gs-text-muted)">{view.learned_note}</Text>
            </Group>
          )}
          <QualityBadges lead={view.lead} />
          <ScoreBreakdown view={view} />
          {view.red_flags && (
            <Alert variant="light" color="red" icon={<IconAlertTriangle size={18} />} title="Red flags">
              {view.red_flags}
            </Alert>
          )}

          {canWrite && <LeadOutreach leadId={view.lead.id} leadUrl={view.lead.url} />}

          <Divider />
          <Stack gap={6}>
            <span className="gs-eyebrow">Brief</span>
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }} lineClamp={18}>
              {view.lead.description}
            </Text>
            {view.lead.skills.length > 0 && (
              <Group gap={6}>
                {view.lead.skills.slice(0, 14).map((s) => (
                  <Badge key={s} variant="default" size="sm">
                    {s}
                  </Badge>
                ))}
              </Group>
            )}
          </Stack>

          <Stack gap={6}>
            <span className="gs-eyebrow">Notes</span>
            <Textarea
              autosize
              minRows={3}
              value={notes}
              onChange={(e) => setNotes(e.currentTarget.value)}
              disabled={!canWrite}
              placeholder="Who you spoke to, next step, follow-up date…"
              maxLength={5000}
            />
            <Group justify="space-between">
              {view.lead.url ? (
                <Anchor href={view.lead.url} target="_blank" rel="noopener noreferrer" size="sm">
                  <Group gap={4}>
                    Open on {view.lead.source} <IconExternalLink size={14} />
                  </Group>
                </Anchor>
              ) : (
                <span />
              )}
              <Button
                size="xs"
                onClick={() => update.mutate({ notes })}
                loading={update.isPending}
                disabled={notes === view.notes}
              >
                Save notes
              </Button>
            </Group>
          </Stack>
        </Stack>
      )}
    </Drawer>
  );
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <Stack gap={0}>
      <span className="gs-eyebrow">{label}</span>
      <Text className="gs-num" size="lg">
        {value}
      </Text>
    </Stack>
  );
}
