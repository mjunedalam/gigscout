import { Badge, Button, Group, Menu, Modal, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconBuildingSkyscraper, IconCheck, IconPlus, IconSelector } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api, messageOf } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const ROLE_LABEL = { owner: "owner", admin: "admin", member: "member", viewer: "viewer" } as const;

/** Which company you are working in. Everything on every page belongs to it. */
export function WorkspaceSwitcher() {
  const { workspace, workspaces, switchWorkspace, isPlatformAdmin } = useAuth();
  const [creating, { open, close }] = useDisclosure();
  const navigate = useNavigate();
  if (!workspace) return null;

  const go = (id: number) => {
    if (id === workspace.id) return;
    switchWorkspace(id);
    navigate("/");
  };

  return (
    <>
      <Menu position="bottom-start" width={280} shadow="md">
        <Menu.Target>
          <UnstyledButton className="gs-panel gs-focus" px="sm" py={6} aria-label={`Workspace: ${workspace.name}. Switch workspace`}>
            <Group gap={8} wrap="nowrap">
              <IconBuildingSkyscraper size={16} color="var(--gs-signal)" />
              <Text size="sm" fw={600} truncate maw={180}>{workspace.name}</Text>
              <IconSelector size={14} color="var(--gs-text-muted)" />
            </Group>
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>Workspaces</Menu.Label>
          {workspaces.map((w) => (
            <Menu.Item key={w.id} onClick={() => go(w.id)}
              leftSection={w.id === workspace.id ? <IconCheck size={14} /> : <span style={{ width: 14 }} />}
              rightSection={<Badge size="xs" variant="light" color="gray">{ROLE_LABEL[w.role]}</Badge>}>
              <Text size="sm" truncate>{w.name}</Text>
            </Menu.Item>
          ))}
          {isPlatformAdmin && (
            <>
              <Menu.Divider />
              <Menu.Item leftSection={<IconPlus size={14} />} onClick={open}>New workspace</Menu.Item>
            </>
          )}
        </Menu.Dropdown>
      </Menu>
      <NewWorkspace opened={creating} onClose={close} onCreated={go} />
    </>
  );
}

function NewWorkspace({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (id: number) => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.workspaces.create(name.trim()),
    onSuccess: async (w) => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      notifications.show({ color: "signal", title: `${w.name} is ready`, message: "Add a company profile, then run the agents." });
      setName("");
      onClose();
      onCreated(w.id);
    },
    onError: (e) => notifications.show({ color: "red", title: "Could not create it", message: messageOf(e) }),
  });
  return (
    <Modal opened={opened} onClose={onClose} title={<span className="gs-eyebrow">New workspace</span>}>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) create.mutate(); }}>
        <Stack>
          <Text size="sm" c="var(--gs-text-muted)">
            A separate company with its own leads, profiles, runs, sources and team. You become its first owner.
          </Text>
          <TextInput label="Company name" placeholder="Bright Studio" value={name} data-autofocus
            onChange={(e) => setName(e.currentTarget.value)} maxLength={120} />
          <Button type="submit" loading={create.isPending} disabled={name.trim().length < 2}>Create workspace</Button>
        </Stack>
      </form>
    </Modal>
  );
}
