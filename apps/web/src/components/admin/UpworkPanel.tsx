import { Alert, Badge, Box, Button, Code, Group, Stack, Text, ThemeIcon } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconBrandUpwork, IconExternalLink } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router";

import { api, messageOf } from "../../lib/api";
import { timeAgo } from "../../lib/format";

const KEY = ["admin", "upwork"];

/** Upwork through its official API: an admin signs in once, then every run searches Upwork jobs too. */
export function UpworkPanel() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: KEY, queryFn: api.admin.upwork });
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    // Upwork sends the browser back here with ?upwork=connected or ?upwork=error&message=…
    const result = params.get("upwork");
    if (!result) return;
    notifications.show(result === "connected"
      ? { color: "signal", title: "Upwork connected", message: "The agents search Upwork jobs from the next run." }
      : { color: "red", autoClose: 10000, title: "Upwork not connected", message: params.get("message") ?? "Sign-in failed" });
    setParams((p) => { p.delete("upwork"); p.delete("message"); return p; }, { replace: true });
    void queryClient.invalidateQueries({ queryKey: ["admin"] });
  }, [params, setParams, queryClient]);

  const connect = useMutation({
    mutationFn: api.admin.connectUpwork,
    onSuccess: ({ url }) => window.location.assign(url),
    onError: (e) => notifications.show({ color: "red", title: "Could not start the Upwork sign-in", message: messageOf(e) }),
  });
  const disconnect = useMutation({
    mutationFn: api.admin.disconnectUpwork,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
  const confirmDisconnect = () => modals.openConfirmModal({
    title: "Disconnect Upwork?",
    children: <Text size="sm">The agents stop searching Upwork. Leads already found stay.</Text>,
    labels: { confirm: "Disconnect", cancel: "Keep it" }, confirmProps: { color: "red" },
    onConfirm: () => disconnect.mutate(),
  });

  const s = status.data;
  return (
    <Box className="gs-panel" p="lg" mt="lg">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm" wrap="nowrap">
          <ThemeIcon radius="xl" variant="light" color={s?.connected ? "signal" : "gray"}><IconBrandUpwork size={18} /></ThemeIcon>
          <Stack gap={0}>
            <Text fw={600}>Upwork</Text>
            <Text size="xs" c="var(--gs-text-muted)">
              {s?.connected
                ? `Connected by ${s.connected_by}${s.connected_at ? ` · ${timeAgo(s.connected_at)}` : ""}. Every run searches Upwork jobs.`
                : "Official Upwork API: an admin signs in once, then every run searches Upwork jobs."}
            </Text>
          </Stack>
        </Group>
        {s?.connected ? (
          <Group gap="xs">
            <Badge color="signal" variant="light">connected</Badge>
            <Button size="xs" variant="subtle" color="red" loading={disconnect.isPending} onClick={confirmDisconnect}>Disconnect</Button>
          </Group>
        ) : (
          <Button size="xs" rightSection={<IconExternalLink size={14} />} disabled={!s?.configured}
            loading={connect.isPending} onClick={() => connect.mutate()}>Connect Upwork</Button>
        )}
      </Group>
      {s && !s.configured && (
        <Alert mt="md" variant="light" color="gray">
          <Text size="sm">
            Needs an approved Upwork API key (apply at upwork.com/developer/keys/apply). Add it to <Code>apps/api/.env</Code> as{" "}
            <Code>GIGSCOUT_UPWORK_CLIENT_ID</Code> and <Code>GIGSCOUT_UPWORK_CLIENT_SECRET</Code>, with this callback URL
            registered on the key: <Code>{`${window.location.origin}/api/admin/upwork/callback`}</Code>
          </Text>
        </Alert>
      )}
      <Text size="xs" c="var(--gs-text-muted)" mt="sm">
        LinkedIn offers no job-search API to outside tools, and its terms forbid scraping, so GigScout does not search it.
      </Text>
    </Box>
  );
}
