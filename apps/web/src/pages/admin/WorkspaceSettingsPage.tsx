import { ActionIcon, Button, Code, CopyButton, Group, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconCopy, IconRefresh } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { DigestSettings } from "../../components/admin/DigestSettings";
import { PageHeader, Panel } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";

/** The workspace itself: its name, its website form address, and the daily digest. */
export default function WorkspaceSettingsPage() {
  const queryClient = useQueryClient();
  const current = useQuery({ queryKey: ["workspace", "current"], queryFn: api.workspaces.current });
  const [name, setName] = useState("");
  useEffect(() => setName(current.data?.name ?? ""), [current.data?.name]);
  const refused = (e: unknown) => notifications.show({ color: "red", title: "Not saved", message: messageOf(e) });
  const rename = useMutation({
    mutationFn: () => api.workspaces.rename(name.trim()),
    onSuccess: (w) => {
      queryClient.setQueryData(["workspace", "current"], w);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      notifications.show({ color: "signal", message: "Workspace renamed" });
    },
    onError: refused,
  });
  const rotate = useMutation({
    mutationFn: api.workspaces.rotateFormKey,
    onSuccess: (w) => {
      queryClient.setQueryData(["workspace", "current"], w);
      notifications.show({ color: "signal", title: "New form address", message: "Update your website's form: the old address no longer works." });
    },
    onError: refused,
  });
  const confirmRotate = () => modals.openConfirmModal({
    title: "Give the website form a new address?",
    children: <Text size="sm">The current address stops working at once. Use this if it leaked or you are getting spam.</Text>,
    labels: { confirm: "New address", cancel: "Keep it" },
    onConfirm: () => rotate.mutate(),
  });
  const formUrl = current.data?.form_path ? `${window.location.origin}${current.data.form_path}` : "";

  return (
    <>
      <PageHeader eyebrow="Admin" title="Workspace" description="Settings for this company: its name, the address your website's contact form posts to, and the daily digest." />
      <Stack gap="lg">
        <Panel eyebrow="Name" title="What this workspace is called">
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) rename.mutate(); }}>
            <Group align="flex-end">
              <TextInput flex="1 1 280px" label="Company name" value={name} maxLength={120} onChange={(e) => setName(e.currentTarget.value)} />
              <Button type="submit" loading={rename.isPending} disabled={name.trim().length < 2 || name.trim() === current.data?.name}>Save</Button>
            </Group>
          </form>
        </Panel>
        <Panel eyebrow="Website form" title="Where your contact form sends enquiries"
          actions={<Button size="xs" variant="subtle" leftSection={<IconRefresh size={14} />} loading={rotate.isPending} onClick={confirmRotate}>New address</Button>}>
          <Text size="sm" c="var(--gs-text-muted)" mb="xs">
            Set your form's action to this address (method POST). Each enquiry becomes an inbound lead in this workspace. Keep it private: it works as a password.
          </Text>
          <Group gap="xs" wrap="nowrap">
            <Code style={{ wordBreak: "break-all", flex: 1 }}>{formUrl || "…"}</Code>
            <CopyButton value={formUrl}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? "Copied" : "Copy"}>
                  <ActionIcon variant="subtle" onClick={copy} aria-label="Copy the form address">{copied ? <IconCheck size={16} /> : <IconCopy size={16} />}</ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
        </Panel>
        <DigestSettings />
      </Stack>
    </>
  );
}
