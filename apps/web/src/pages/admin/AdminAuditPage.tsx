import { Alert, Badge, Box, Code, Group, Select, Skeleton, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";
import { dateTime } from "../../lib/format";

const AREA_COLORS: Record<string, string> = {
  auth: "gray", user: "violet", lead: "blue", run: "signal", schedule: "yellow", profile: "teal", source: "orange",
};

export default function AdminAuditPage() {
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api.admin.audit(500), refetchInterval: 30_000 });
  const [area, setArea] = useState<string | null>(null);
  const [actor, setActor] = useState<string | null>(null);
  const actors = [...new Set((audit.data ?? []).map((a) => a.actor))].sort();
  const rows = (audit.data ?? []).filter((a) => (!area || a.action.startsWith(`${area}.`)) && (!actor || a.actor === actor));

  return (
    <>
      <PageHeader eyebrow="Admin" title="Audit log" description="Every sign-in and change, newest first."
        actions={
          <Group gap="xs">
            <Select placeholder="Everyone" clearable value={actor} onChange={setActor} data={actors} w={220} aria-label="Filter by person" />
            <Select placeholder="All areas" clearable value={area} onChange={setArea} data={Object.keys(AREA_COLORS)} w={180} aria-label="Filter by area" />
          </Group>
        } />
      {audit.isError && <Alert color="red">{messageOf(audit.error)}</Alert>}
      {audit.isPending ? (
        <Skeleton h={400} radius="lg" />
      ) : (
        <Box className="gs-panel" style={{ overflowX: "auto" }}>
          <Table miw={820}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={170}>When</Table.Th>
                <Table.Th w={220}>Who</Table.Th>
                <Table.Th w={170}>Action</Table.Th>
                <Table.Th>Target & detail</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((a) => (
                <Table.Tr key={a.id}>
                  <Table.Td><Text size="xs" className="gs-mono">{dateTime(a.at)}</Text></Table.Td>
                  <Table.Td><Text size="sm">{a.actor}</Text></Table.Td>
                  <Table.Td><Badge color={AREA_COLORS[a.action.split(".")[0] ?? ""] ?? "gray"}>{a.action}</Badge></Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      {a.target && <Text size="sm" className="gs-mono">{a.target}</Text>}
                      {Object.keys(a.detail).length > 0 && <Code>{JSON.stringify(a.detail)}</Code>}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Box>
      )}
    </>
  );
}
