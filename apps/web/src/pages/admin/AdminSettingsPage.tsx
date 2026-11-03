import { Alert, Box, Skeleton, Table, Text, TextInput } from "@mantine/core";
import { IconInfoCircle, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DigestSettings } from "../../components/admin/DigestSettings";
import { PageHeader } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";

export default function AdminSettingsPage() {
  const settings = useQuery({ queryKey: ["admin", "settings"], queryFn: api.admin.settings });
  const [filter, setFilter] = useState("");
  const rows = Object.entries(settings.data ?? {}).filter(([key]) => key.includes(filter.toLowerCase()));

  return (
    <>
      <PageHeader eyebrow="Admin" title="Configuration" description="The daily digest, and the settings this server is running with. Secrets are masked." />
      <DigestSettings />
      <Alert icon={<IconInfoCircle size={18} />} variant="light" mb="md">
        Change values in <code>apps/api/.env</code> as <code>GIGSCOUT_&lt;NAME&gt;</code> and restart the API.
      </Alert>
      {settings.isError && <Alert color="red">{messageOf(settings.error)}</Alert>}
      <TextInput mb="md" maw={360} placeholder="Filter settings" leftSection={<IconSearch size={16} />}
        value={filter} onChange={(e) => setFilter(e.currentTarget.value)} />
      {settings.isPending ? (
        <Skeleton h={400} radius="lg" />
      ) : (
        <Box className="gs-panel" style={{ overflowX: "auto" }}>
          <Table>
            <Table.Tbody>
              {rows.map(([key, value]) => (
                <Table.Tr key={key}>
                  <Table.Td w="40%"><Text size="sm" className="gs-mono">GIGSCOUT_{key.toUpperCase()}</Text></Table.Td>
                  <Table.Td><Text size="sm" className="gs-mono" c="var(--gs-text-muted)" style={{ wordBreak: "break-all" }}>{JSON.stringify(value)}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Box>
      )}
    </>
  );
}
