import { Alert, Button, Group, Text } from "@mantine/core";
import { IconAlertTriangle, IconClockHour4 } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const TRIAL_WARNING_DAYS = 3;
const DAY_MS = 86_400_000;

/** Tells everyone when the plan stops agent runs, and admins how to fix it; a quiet note as a trial nears its end. */
export function BillingBanner() {
  const { isAdmin, workspace } = useAuth();
  const billing = useQuery({ queryKey: ["billing"], queryFn: api.billing.get, staleTime: 60_000, enabled: !!workspace });
  const b = billing.data;
  if (!b?.enabled) return null;
  const action = isAdmin
    ? <Button component={Link} to="/admin/billing" size="xs" variant="white" color="dark">Choose a plan</Button>
    : <Text size="xs">Ask an owner or admin of {workspace?.name} to renew it.</Text>;
  if (!b.can_work) {
    return (
      <Alert color="red" variant="filled" mb="lg" icon={<IconAlertTriangle size={18} />} title="Agent runs are paused">
        <Group justify="space-between" gap="sm">
          <Text size="sm">{b.reason} Your leads stay available.</Text>
          {action}
        </Group>
      </Alert>
    );
  }
  const daysLeft = b.plan === "trial" && b.trial_ends_at ? Math.ceil((Date.parse(b.trial_ends_at) - Date.now()) / DAY_MS) : null;
  if (daysLeft !== null && daysLeft <= TRIAL_WARNING_DAYS) {
    return (
      <Alert color="blue" variant="light" mb="lg" icon={<IconClockHour4 size={18} />}>
        <Group justify="space-between" gap="sm">
          <Text size="sm">Your free trial ends in {daysLeft} day{daysLeft === 1 ? "" : "s"}.</Text>
          {isAdmin && <Button component={Link} to="/admin/billing" size="xs" variant="light">See plans</Button>}
        </Group>
      </Alert>
    );
  }
  return null;
}
