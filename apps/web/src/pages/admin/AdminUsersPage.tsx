import type { Member, WorkspaceRole } from "@gigscout/api-client";
import {
  Avatar,
  Badge,
  Box,
  Button,
  Group,
  Menu,
  Modal,
  PasswordInput,
  SegmentedControl,
  Skeleton,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconDots, IconKey, IconUserMinus, IconUserPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { timeAgo } from "../../lib/format";

const MIN_PASSWORD = 10;
const ROLES: WorkspaceRole[] = ["viewer", "member", "admin", "owner"];

export default function AdminUsersPage() {
  const { user: me, workspace } = useAuth();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: api.admin.users });
  const [inviteOpen, invite] = useDisclosure();
  const [resetting, setResetting] = useState<Member | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  const refused = (error: unknown) => notifications.show({ color: "red", title: "Change refused", message: messageOf(error) });

  const update = useMutation({
    mutationFn: ({ id, change }: { id: number; change: Parameters<typeof api.admin.updateUser>[1] }) => api.admin.updateUser(id, change),
    onSuccess: refresh,
    onError: refused,
  });
  const remove = useMutation({ mutationFn: api.admin.removeUser, onSuccess: refresh, onError: refused });

  return (
    <>
      <PageHeader eyebrow={workspace?.name ?? "Admin"} title="Team"
        description="Owners and admins manage profiles, schedules, connectors and the team. Members work leads and start runs. Viewers can look but not change anything. Only owners make owners."
        actions={<Button leftSection={<IconUserPlus size={18} />} onClick={invite.open}>Add someone</Button>} />
      {users.isPending && <Skeleton h={300} radius="lg" />}
      {users.data && (
        <Box className="gs-panel" style={{ overflowX: "auto" }}>
          <Table miw={760}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>User</Table.Th>
                <Table.Th w={200}>Role</Table.Th>
                <Table.Th w={110}>Active</Table.Th>
                <Table.Th w={140}>Last sign-in</Table.Th>
                <Table.Th w={60} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {users.data.map((u) => (
                <Table.Tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.55 }}>
                  <Table.Td>
                    <Group gap="sm" wrap="nowrap">
                      <Avatar radius="xl" color={u.role === "member" ? "violet" : "signal"}>{u.name.slice(0, 2).toUpperCase()}</Avatar>
                      <Stack gap={0}>
                        <Text size="sm" fw={600}>
                          {u.name} {u.id === me?.id && <Badge size="xs" ml={4}>you</Badge>}
                          {u.platform_admin && <Badge size="xs" ml={4} variant="light" color="orange">platform admin</Badge>}
                        </Text>
                        <Text size="xs" c="var(--gs-text-muted)">{u.email}</Text>
                      </Stack>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <SegmentedControl size="xs" value={u.role} data={ROLES}
                      onChange={(role) => update.mutate({ id: u.id, change: { role: role as WorkspaceRole } })} />
                  </Table.Td>
                  <Table.Td>
                    <Switch checked={u.is_active} disabled={u.id === me?.id} aria-label="Active"
                      onChange={(e) => update.mutate({ id: u.id, change: { is_active: e.currentTarget.checked } })} />
                  </Table.Td>
                  <Table.Td><Text size="xs" className="gs-mono" c="var(--gs-text-muted)">{timeAgo(u.last_login_at)}</Text></Table.Td>
                  <Table.Td>
                    <Menu position="bottom-end">
                      <Menu.Target><Button variant="subtle" size="compact-sm" aria-label="More"><IconDots size={16} /></Button></Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconKey size={16} />} onClick={() => setResetting(u)}>Reset password</Menu.Item>
                        {u.id !== me?.id && (
                          <Menu.Item color="red" leftSection={<IconUserMinus size={16} />} onClick={() => remove.mutate(u.id)}>
                            Remove from workspace
                          </Menu.Item>
                        )}
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Box>
      )}
      <InviteModal opened={inviteOpen} onClose={invite.close} />
      <ResetModal user={resetting} onClose={() => setResetting(null)} onSubmit={(password) =>
        resetting && update.mutate({ id: resetting.id, change: { password } }, {
          onSuccess: () => { setResetting(null); notifications.show({ color: "signal", message: "Password reset; their sessions were signed out" }); },
        })} />
    </>
  );
}

function InviteModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const form = useForm({
    initialValues: { name: "", email: "", role: "member" as WorkspaceRole, password: "" },
    validate: {
      name: (v) => (v.trim() ? null : "Required"),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Enter a valid email"),
      password: (v) => (!v || v.length >= MIN_PASSWORD ? null : `At least ${MIN_PASSWORD} characters`),
    },
  });
  const create = useMutation({
    mutationFn: (v: typeof form.values) => api.admin.createUser({ ...v, password: v.password || undefined }),
    onSuccess: (_, v) => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      notifications.show({ color: "signal", message: v.password ? "Account created. Share the temporary password securely." : "Added to the workspace." });
      form.reset();
      onClose();
    },
    onError: (error) => notifications.show({ color: "red", message: messageOf(error) }),
  });
  return (
    <Modal opened={opened} onClose={onClose} title={<span className="gs-eyebrow">Add someone</span>}>
      <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
        <Stack>
          <TextInput label="Name" {...form.getInputProps("name")} />
          <TextInput label="Email" type="email" {...form.getInputProps("email")} />
          <SegmentedControl data={ROLES} {...form.getInputProps("role")} />
          <PasswordInput label="Temporary password" {...form.getInputProps("password")}
            description={`For a new account: at least ${MIN_PASSWORD} characters. Leave empty if they already have a GigScout account.`} />
          <Button type="submit" loading={create.isPending}>Add to workspace</Button>
        </Stack>
      </form>
    </Modal>
  );
}

function ResetModal({ user, onClose, onSubmit }: { user: Member | null; onClose: () => void; onSubmit: (p: string) => void }) {
  const [password, setPassword] = useState("");
  return (
    <Modal opened={!!user} onClose={onClose} title={<span className="gs-eyebrow">Reset password · {user?.email}</span>}>
      <Stack>
        <PasswordInput label="New password" value={password} onChange={(e) => setPassword(e.currentTarget.value)}
          error={password && password.length < MIN_PASSWORD ? `At least ${MIN_PASSWORD} characters` : null} />
        <Button disabled={password.length < MIN_PASSWORD} onClick={() => { onSubmit(password); setPassword(""); }}>Reset password</Button>
      </Stack>
    </Modal>
  );
}
