import type { Billing, BillingPlan } from "@gigscout/api-client";
import { Alert, Badge, Box, Button, Group, Progress, SimpleGrid, Skeleton, Stack, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconCreditCard, IconExternalLink, IconInfoCircle, IconRocket } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router";

import { PageHeader, Panel } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime } from "../../lib/format";

const BILLING_KEY = ["billing"];
const PLAN_LABEL: Record<Billing["plan"], string> = { unlimited: "Unlimited", trial: "Free trial", starter: "Starter", growth: "Growth" };
const STATUS_COLOR: Record<string, string> = { active: "signal", trialing: "blue", past_due: "orange", unpaid: "red", canceled: "gray", expired: "red", unlimited: "signal" };

/** The workspace's plan, what it has used, and Stripe for paying and managing it. */
export default function BillingPage() {
  const { workspace } = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const billing = useQuery({ queryKey: BILLING_KEY, queryFn: api.billing.get });
  const go = (url: string) => window.location.assign(url);
  const checkout = useMutation({ mutationFn: api.billing.checkout, onSuccess: (r) => go(r.url),
    onError: (e) => notifications.show({ color: "red", title: "Could not open checkout", message: messageOf(e) }) });
  const portal = useMutation({ mutationFn: api.billing.portal, onSuccess: (r) => go(r.url),
    onError: (e) => notifications.show({ color: "red", title: "Could not open billing", message: messageOf(e) }) });

  // back from Stripe: the plan starts when Stripe's webhook arrives, usually within seconds
  const result = params.get("checkout");
  useEffect(() => {
    if (!result) return;
    notifications.show(result === "done"
      ? { color: "signal", title: "Thank you", message: "Your plan starts as soon as Stripe confirms the payment." }
      : { color: "gray", message: "Checkout cancelled: nothing was charged." });
    setParams({}, { replace: true });
    const refresh = setInterval(() => void queryClient.invalidateQueries({ queryKey: BILLING_KEY }), 3000);
    const stop = setTimeout(() => clearInterval(refresh), 30000);
    return () => { clearInterval(refresh); clearTimeout(stop); };
  }, [result, setParams, queryClient]);

  const b = billing.data;
  return (
    <>
      <PageHeader eyebrow={workspace?.name ?? "Admin"} title="Billing" description="Your plan, what this month has used, and payment. Card details stay with Stripe."
        actions={b?.can_manage && (
          <Button variant="light" leftSection={<IconCreditCard size={16} />} rightSection={<IconExternalLink size={14} />}
            loading={portal.isPending} onClick={() => portal.mutate()}>Manage billing</Button>
        )} />
      {billing.isError && <Alert color="red">{messageOf(billing.error)}</Alert>}
      {billing.isPending && <Skeleton h={320} radius="lg" />}
      {b && !b.enabled && (
        <Alert icon={<IconInfoCircle size={18} />} variant="light" title={b.plan === "unlimited" ? "No limits here" : "Billing is off"}>
          This workspace has no plan limits: billing is off on this server, or the workspace is exempt.
        </Alert>
      )}
      {b?.enabled && (
        <Stack gap="lg">
          <Panel>
            <Group justify="space-between" align="flex-start" wrap="wrap" gap="lg">
              <Stack gap={4}>
                <span className="gs-eyebrow">Current plan</span>
                <Group gap="sm">
                  <Text fw={700} fz={28} className="gs-display">{PLAN_LABEL[b.plan]}</Text>
                  <Badge variant="light" color={STATUS_COLOR[b.status] ?? "gray"}>{b.status.replace("_", " ")}</Badge>
                </Group>
                <Text size="sm" c="var(--gs-text-muted)">
                  {b.trial_ends_at && b.plan === "trial" ? `Trial ${b.can_work ? "ends" : "ended"} ${dateTime(b.trial_ends_at)}`
                    : b.current_period_end ? `Renews ${dateTime(b.current_period_end)}` : ""}
                </Text>
              </Stack>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" style={{ flex: "1 1 360px", maxWidth: 520 }}>
                <Usage label="People" used={b.members} limit={b.members_limit} />
                <Usage label="Agent runs this month" used={b.runs_this_month} limit={b.runs_limit} />
              </SimpleGrid>
            </Group>
          </Panel>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
            {b.plans.map((p) => (
              <PlanCard key={p.id} plan={p} current={b.plan === p.id && b.can_work}
                busy={checkout.isPending && checkout.variables === p.id} onChoose={() => checkout.mutate(p.id)} />
            ))}
          </SimpleGrid>
        </Stack>
      )}
    </>
  );
}

function Usage({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Text size="sm" c="var(--gs-text-muted)">{label}</Text>
        <Text size="sm" className="gs-num">{used}{limit !== null ? ` / ${limit}` : ""}</Text>
      </Group>
      <Progress value={pct} color={pct >= 90 ? "red" : pct >= 70 ? "orange" : "signal"} size="sm" radius="xl"
        aria-label={`${label}: ${used}${limit !== null ? ` of ${limit}` : ""}`} />
    </Stack>
  );
}

function PlanCard({ plan, current, busy, onChoose }: { plan: BillingPlan; current: boolean; busy: boolean; onChoose: () => void }) {
  return (
    <Box className="gs-panel gs-lift" p="xl" style={current ? { borderColor: "var(--gs-signal)" } : undefined}>
      <Group justify="space-between" mb="md">
        <Group gap="sm">
          <ThemeIcon variant="light" color={plan.id === "growth" ? "violet" : "signal"} radius="xl"><IconRocket size={16} /></ThemeIcon>
          <Text fw={700} size="lg">{plan.label}</Text>
        </Group>
        {current && <Badge color="signal" variant="light">Your plan</Badge>}
      </Group>
      <Text fz={32} fw={600} className="gs-num" mb="md">{plan.price ?? "—"}</Text>
      <Stack gap={6} mb="lg">
        {[`Up to ${plan.members} people`, `${plan.runs_per_month.toLocaleString()} agent runs a month`, "Every source, quality check and the AI agent team", "Daily digest, outreach and CRM sync"].map((line) => (
          <Group key={line} gap={8} wrap="nowrap"><IconCheck size={14} color="var(--gs-signal)" /><Text size="sm">{line}</Text></Group>
        ))}
      </Stack>
      <Button fullWidth variant={current ? "default" : "filled"} disabled={current} loading={busy} onClick={onChoose}>
        {current ? "Current plan" : `Choose ${plan.label}`}
      </Button>
    </Box>
  );
}
