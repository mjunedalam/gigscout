import type { LibrarySource } from "@gigscout/api-client";
import { Badge, Box, Button, Group, Select, SimpleGrid, Skeleton, Stack, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBooks, IconCheck, IconPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, messageOf } from "../../lib/api";

const KIND_LABEL: Record<LibrarySource["lead_kind"], string> = {
  project: "projects", contract: "contracts", hiring: "companies hiring",
};

/** Checked public websites worth searching for a kind of company, each connected in one click. */
export function SourceLibrary() {
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["profiles", "templates"], queryFn: api.profiles.templates });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles.list });
  const [companyType, setCompanyType] = useState<string | null>(null);
  useEffect(() => {
    // Start with what the first company profile says it is.
    if (companyType === null && profiles.data) setCompanyType(profiles.data[0]?.data.company_type || "Software agency");
  }, [companyType, profiles.data]);

  const library = useQuery({
    queryKey: ["admin", "library", companyType],
    queryFn: () => api.admin.connectorLibrary(companyType ?? undefined),
    enabled: companyType !== null,
  });
  const add = useMutation({
    mutationFn: (s: LibrarySource) => api.admin.addConnector(s.name, s.url, s.lead_kind),
    onSuccess: (site) => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "sources"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "library"] });
      notifications.show({ color: "signal", title: `Connected: ${site.label ?? site.name}`, message: "The agents search it from the next run." });
    },
    onError: (e) => notifications.show({ color: "red", autoClose: 10000, title: "Website not added", message: messageOf(e) }),
  });

  const types = [...new Set([...(templates.data?.map((t) => t.company_type) ?? []), ...(companyType ? [companyType] : [])])];
  const entries = library.data ?? [];
  const remaining = entries.filter((e) => !e.added).length;

  return (
    <Box className="gs-panel" p="lg" mt="lg">
      <Group justify="space-between" align="flex-end" mb="md" wrap="wrap">
        <Group gap="sm">
          <ThemeIcon radius="xl" variant="light"><IconBooks size={18} /></ThemeIcon>
          <Stack gap={0}>
            <Text fw={600}>Source library</Text>
            <Text size="xs" c="var(--gs-text-muted)">
              Public sites we checked for your kind of company. Each one is checked again when you add it.
            </Text>
          </Stack>
        </Group>
        <Select label="Company type" w={240} data={types} value={companyType} allowDeselect={false}
          onChange={setCompanyType} searchable />
      </Group>
      <Text size="xs" c="var(--gs-text-muted)" mb="sm">
        Public tenders are built in: UK Contracts Finder, Find a Tender and EU TED (US SAM.gov with a free key).
      </Text>
      {library.isPending && <Skeleton h={120} radius="md" />}
      {library.data && (
        <Text size="xs" c="var(--gs-text-muted)" mb="sm">
          {entries.length} sites for {companyType} · {remaining ? `${remaining} not connected yet` : "all connected"}
        </Text>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="sm">
        {entries.map((s) => (
          <Box key={s.url} p="sm" style={{ border: "1px solid var(--gs-line)", borderRadius: 10 }}>
            <Group justify="space-between" wrap="nowrap" align="flex-start" gap="xs">
              <Stack gap={2} style={{ minWidth: 0 }}>
                <Text fw={600} size="sm" truncate>{s.name}</Text>
                <Text size="xs" c="var(--gs-text-muted)" lineClamp={2}>{s.description}</Text>
              </Stack>
              {s.added ? (
                <Badge color="signal" variant="light" leftSection={<IconCheck size={12} />}>added</Badge>
              ) : (
                <Button size="compact-xs" variant="light" leftSection={<IconPlus size={12} />}
                  loading={add.isPending && add.variables?.url === s.url} onClick={() => add.mutate(s)}
                  aria-label={`Add ${s.name}`}>Add</Button>
              )}
            </Group>
            <Group gap={6} mt={6}>
              <Badge size="xs" variant="outline" color="gray">{KIND_LABEL[s.lead_kind]}</Badge>
              <Badge size="xs" variant="outline" color="gray">{s.region}</Badge>
            </Group>
          </Box>
        ))}
      </SimpleGrid>
    </Box>
  );
}
